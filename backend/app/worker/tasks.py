"""Celery Canvas DAG for a durable end-to-end evaluation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import chain, chord, group

from app.core.celery_app import celery_app
from app.engine.aggregator import aggregate_score
from app.infrastructure.database import async_session_factory
from app.models.evaluation import Evaluation
from app.models.submission import Submission
from app.services.evaluation_execution_service import execute_submission
from app.services.trace_service import trace_service
from app.services.websocket_service import publish_progress
from app.infrastructure.minio import minio_client
from app.services.agent_package import contract_from_dict
from app.services.image_builder import get_image_builder
from app.services.submission_service import _extract_package, _cleanup_dir
from app.services.api_key_vault import APIKeyVault


def _run(coroutine):
    return asyncio.run(coroutine)


async def _build_submission(submission_id: str) -> dict:
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        if submission is None:
            raise LookupError(f"Submission {submission_id} 不存在")
        submission.status = "building"
        submission.build_status = "building"
        submission.status_message = "正在隔离构建 Agent 镜像"
        package_path = submission.source_package_path
        source_hash = submission.source_package_hash
        contract = contract_from_dict(dict(submission.config)["package_contract"])
        await db.commit()
    await publish_progress(submission_id, "status_changed", {"stage": "building", "percent": 15})
    package = minio_client.get_package(package_path)
    source_root = _extract_package(package, package_path)
    try:
        result = await get_image_builder().build(submission_id, source_root, contract, source_hash)
        log_path = minio_client.upload_text(f"submissions/{submission_id}/build.log", result.build_log)
        scan_path = minio_client.upload_json(f"submissions/{submission_id}/image-scan.json", result.scan_report)
        sbom_path = minio_client.upload_json(f"submissions/{submission_id}/sbom.cdx.json", result.sbom)
        async with async_session_factory() as db:
            submission = await db.get(Submission, submission_id)
            submission.image_ref = result.image_ref
            submission.image_digest = result.image_digest
            submission.build_log_path = log_path
            submission.sbom_path = sbom_path
            submission.image_scan_path = scan_path
            submission.build_status = "image_ready"
            submission.status = "image_ready"
            submission.status_message = f"镜像已构建并通过安全检查（报告: {scan_path}）"
            await db.commit()
        await publish_progress(submission_id, "status_changed", {"stage": "image_ready", "percent": 30})
        return {"submission_id": submission_id, "image_ref": result.image_ref, "image_digest": result.image_digest}
    except Exception as exc:
        failure_log = getattr(exc, "build_log", "") or str(exc)
        try:
            failure_log_path = minio_client.upload_text(f"submissions/{submission_id}/build.log", failure_log)
        except Exception:
            failure_log_path = None
        async with async_session_factory() as db:
            submission = await db.get(Submission, submission_id)
            if submission:
                submission.build_status = "build_failed"
                submission.status = "build_failed"
                submission.status_message = str(exc)[:2000]
                submission.build_log_path = failure_log_path
                await db.commit()
        await publish_progress(submission_id, "failed", {"stage": "build_failed", "error": str(exc)[:500]})
        raise
    finally:
        _cleanup_dir(source_root)


@celery_app.task(name="app.worker.tasks.build_submission_image", queue="build")
def build_submission_image(submission_id: str) -> dict:
    try:
        return _run(_build_submission(submission_id))
    except Exception as exc:
        _run(_ensure_build_failure(submission_id, exc))
        raise


async def _ensure_build_failure(submission_id: str, exc: Exception) -> None:
    """Cover failures that happen before the main build try/finally starts."""
    changed = False
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        if submission and submission.build_status != "build_failed":
            submission.build_status = "build_failed"
            submission.status = "build_failed"
            submission.status_message = str(exc)[:2000]
            await db.commit()
            changed = True
    if changed:
        await publish_progress(submission_id, "failed", {"stage": "build_failed", "error": str(exc)[:500]})


async def _validate(submission_id: str, evaluation_id: str | None) -> dict:
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        if submission is None:
            raise LookupError(f"Submission {submission_id} 不存在")
        if submission.status != "image_ready" or not submission.image_ref:
            raise ValueError(f"Submission 状态不允许评测: {submission.status}")
        if evaluation_id:
            evaluation = await db.get(Evaluation, evaluation_id)
            if evaluation is None:
                raise LookupError(f"Evaluation {evaluation_id} 不存在")
            evaluation.status = "running"
            evaluation.started_at = datetime.now(timezone.utc)
            await db.commit()
        await publish_progress(submission_id, "status_changed", {"stage": "validated", "percent": 10})
        return {
            "submission_id": submission_id,
            "evaluation_id": evaluation_id,
            "horizon": submission.horizon,
            "stage": "validated",
        }


@celery_app.task(name="app.worker.tasks.validate_submission")
def validate_submission(submission_id: str, evaluation_id: str | None = None) -> dict:
    try:
        return _run(_validate(submission_id, evaluation_id))
    except Exception as exc:
        if evaluation_id:
            _run(APIKeyVault.purge(evaluation_id))
            _run(_mark_failed(evaluation_id, submission_id, str(exc)))
        raise


@celery_app.task(name="app.worker.tasks.deploy_sandbox")
def deploy_sandbox(context: dict) -> dict:
    evaluation_id = context.get("evaluation_id")
    if not evaluation_id:
        # Canvas construction/unit tests may exercise the task without durable
        # records. Production calls always supply an evaluation ID.
        return {**context, "stage": "sandbox_ready"}
    _run(publish_progress(context["submission_id"], "status_changed", {"stage": "sandbox_creating", "percent": 20}))
    try:
        result = _run(execute_submission(context["submission_id"], evaluation_id))
    except Exception as exc:
        _run(_mark_failed(evaluation_id, context["submission_id"], str(exc)))
        raise
    _run(publish_progress(context["submission_id"], "progress", {"stage": "evaluated", "percent": 75}))
    return result


def _dimension(context: dict, name: str) -> dict:
    inputs = context.get("evaluation_inputs", {}).get(name, {})
    return {
        "evaluation_id": context.get("evaluation_id"),
        "trace": context.get("trace"),
        "dimension": name,
        "score": inputs.get("score"),
        "details": inputs.get("details", {}),
    }


@celery_app.task(name="app.worker.tasks.run_result_eval")
def run_result_eval(context):
    return _dimension(context, "result")


@celery_app.task(name="app.worker.tasks.run_trajectory_eval")
def run_trajectory_eval(context):
    return _dimension(context, "trajectory")


@celery_app.task(name="app.worker.tasks.run_efficiency_eval")
def run_efficiency_eval(context):
    return _dimension(context, "efficiency")


@celery_app.task(name="app.worker.tasks.run_security_eval")
def run_security_eval(context):
    return _dimension(context, "security")


@celery_app.task(name="app.worker.tasks.aggregate_and_report")
def aggregate_and_report(results: list[dict], horizon: str = "short") -> dict:
    scores = {item["dimension"]: item["score"] for item in results}
    base = {
        "evaluation_id": results[0].get("evaluation_id") if results else None,
        "trace": results[0].get("trace") if results else None,
        "dimension_details": {item["dimension"]: item.get("details", {}) for item in results},
    }
    if any(value is None for value in scores.values()):
        return {**base, "status": "needs_review", "dimensions": scores}
    return {**base, "status": "completed", **aggregate_score(scores, horizon)}


async def _persist(result: dict) -> dict:
    evaluation_id = result.get("evaluation_id")
    if not evaluation_id:
        return result
    async with async_session_factory() as db:
        evaluation = await db.get(Evaluation, evaluation_id)
        if evaluation is None:
            raise LookupError(f"Evaluation {evaluation_id} 不存在")
        evaluation.status = result["status"]
        evaluation.overall_score = result.get("overall_score")
        evaluation.grade = result.get("grade")
        scores = result.get("dimensions")
        evaluation.dimensions = scores
        evaluation.radar_chart_data = {
            "dimensions": list(scores or {}),
            "scores": list((scores or {}).values()),
            "benchmarks": [],
        }
        evaluation.report_full = {key: value for key, value in result.items() if key != "trace"}
        evaluation.completed_at = datetime.now(timezone.utc)
        if result.get("trace"):
            await trace_service.save_trace(db, evaluation_id, result["trace"])
        await db.commit()
        submission_id = str(evaluation.submission_id)
    await publish_progress(submission_id, "completed" if result["status"] == "completed" else "needs_review", {"evaluation_id": evaluation_id, "status": result["status"], "percent": 100})
    return {key: value for key, value in result.items() if key != "trace"}


async def _mark_failed(evaluation_id: str, submission_id: str, error: str) -> None:
    async with async_session_factory() as db:
        evaluation = await db.get(Evaluation, evaluation_id)
        if evaluation:
            evaluation.status = "failed"
            evaluation.report_full = {"status": "failed", "error": error[:2000]}
            evaluation.completed_at = datetime.now(timezone.utc)
            await db.commit()
    await publish_progress(submission_id, "failed", {"evaluation_id": evaluation_id, "error": error[:500], "percent": 100})


@celery_app.task(name="app.worker.tasks.finalize_evaluation")
def finalize_evaluation(result: dict) -> dict:
    return _run(_persist(result))


def build_evaluation_dag(submission_id: str, evaluation_id: str | None = None, horizon: str = "short"):
    dimensions = group(
        run_result_eval.s(),
        run_trajectory_eval.s(),
        run_efficiency_eval.s(),
        run_security_eval.s(),
    )
    parallel_and_aggregate = chord(dimensions, aggregate_and_report.s(horizon))
    return chain(
        validate_submission.s(submission_id, evaluation_id),
        deploy_sandbox.s(),
        parallel_and_aggregate,
        finalize_evaluation.s(),
    )
