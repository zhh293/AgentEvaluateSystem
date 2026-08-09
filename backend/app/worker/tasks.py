"""Celery Canvas DAG for a durable end-to-end evaluation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone

from celery import chain, chord, group
from sqlalchemy import select

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
from app.models.artifact import VerifiedManifest
from app.services.manifest_service import bind_service_images, manifest_contract_payload
from app.services.case_set_service import case_set_service
from app.services.case_execution_service import execute_evaluation_case
from app.models.case_set import EvaluationCase, ExecutionAttempt
from app.services.lifecycle import (
    EVALUATION_TRANSITIONS, SUBMISSION_TRANSITIONS, EvaluationStatus,
    SubmissionStatus, transition,
)


def _run(coroutine):
    return asyncio.run(coroutine)


async def _build_submission(submission_id: str) -> dict:
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        if submission is None:
            raise LookupError(f"Submission {submission_id} 不存在")
        transition(submission, SubmissionStatus.BUILDING, SUBMISSION_TRANSITIONS)
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
            manifest_row = (await db.execute(
                select(VerifiedManifest).where(VerifiedManifest.submission_id == submission.id)
            )).scalar_one_or_none()
            if manifest_row is None:
                raise RuntimeError("Submission 缺少 Verified Manifest")
            bound_manifest = bind_service_images(dict(manifest_row.manifest), result.service_images)
            manifest_row.manifest = bound_manifest
            manifest_row.manifest_digest = hashlib.sha256(
                json.dumps(bound_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            ).hexdigest()
            transition(submission, SubmissionStatus.IMAGE_SCANNING, SUBMISSION_TRANSITIONS)
            submission.image_ref = result.image_ref
            submission.image_digest = result.image_digest
            durable_config = dict(submission.config or {})
            durable_config["service_images"] = result.service_images
            durable_config["package_contract"] = manifest_contract_payload(bound_manifest)
            durable_config["verified_manifest_digest"] = manifest_row.manifest_digest
            submission.config = durable_config
            submission.build_log_path = log_path
            submission.sbom_path = sbom_path
            submission.image_scan_path = scan_path
            submission.build_status = "image_ready"
            transition(submission, SubmissionStatus.IMAGE_READY, SUBMISSION_TRANSITIONS)
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


@celery_app.task(name="app.worker.tasks.generate_submission_case_set", queue="case-generation")
def generate_submission_case_set(submission_id: str, target_count: int | None = None) -> dict:
    async def generate() -> dict:
        async with async_session_factory() as db:
            case_set = await case_set_service.generate(db, submission_id, target_count)
            return {"case_set_id": str(case_set.id), "submission_id": submission_id,
                    "status": case_set.status, "actual_case_count": case_set.actual_case_count}
    return _run(generate())


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
            transition(evaluation, EvaluationStatus.RUNNING, EVALUATION_TRANSITIONS)
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


@celery_app.task(name="app.worker.tasks.run_evaluation_case")
def run_evaluation_case(submission_id: str, evaluation_id: str, evaluation_case_id: str) -> dict:
    try:
        result = _run(execute_evaluation_case(submission_id, evaluation_id, evaluation_case_id))
        result["evaluation_id"] = evaluation_id
        return result
    except Exception as exc:
        async def persist_failure() -> dict:
            async with async_session_factory() as db:
                case = await db.get(EvaluationCase, evaluation_case_id)
                if case is None:
                    raise LookupError("EvaluationCase 不存在")
                case.status = "failed"
                case.error_code = "CASE_EXECUTION_FAILED"
                case.error_message = str(exc)[:2000]
                case.dimension_scores = {"result": 0.0}
                case.completed_at = datetime.now(timezone.utc)
                attempt = (await db.execute(
                    select(ExecutionAttempt).where(
                        ExecutionAttempt.evaluation_case_id == case.id,
                        ExecutionAttempt.status == "running",
                    ).order_by(ExecutionAttempt.attempt_number.desc()).limit(1)
                )).scalar_one_or_none()
                if attempt:
                    attempt.status = "failed"
                    attempt.error_code = "CASE_EXECUTION_FAILED"
                    attempt.error_message = str(exc)[:2000]
                    attempt.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return {
                    "evaluation_id": evaluation_id, "case_id": case.case_key,
                    "status": "failed", "dimensions": {"result": 0.0},
                    "unknown_weight_ratio": 1.0, "critical_failure": False,
                    "error": str(exc)[:2000], "trace": {"spans": []},
                }
        return _run(persist_failure())


@celery_app.task(name="app.worker.tasks.aggregate_case_results")
def aggregate_case_results(results: list[dict], horizon: str = "short") -> dict:
    names = ("result", "trajectory", "efficiency", "security")
    buckets: dict[str, list[float]] = {name: [] for name in names}
    unknown_ratios: list[float] = []
    critical_failure = False
    combined_spans: list[dict] = []
    for result in results:
        for name, score in (result.get("dimensions") or {}).items():
            if name in buckets and isinstance(score, (int, float)):
                buckets[name].append(float(score))
        unknown_ratios.append(float(result.get("unknown_weight_ratio", 0) or 0))
        critical_failure = critical_failure or bool(result.get("critical_failure"))
        case_key = str(result.get("case_id", "unknown"))
        for raw_span in (result.get("trace") or {}).get("spans", []):
            span = dict(raw_span)
            original_id = str(span.get("span_id", ""))
            original_parent = span.get("parent_span_id")
            span["span_id"] = f"{case_key}:{original_id}"
            if original_parent:
                span["parent_span_id"] = f"{case_key}:{original_parent}"
            attributes = dict(span.get("attributes") or {})
            attributes["agenteval.case_id"] = case_key
            span["attributes"] = attributes
            combined_spans.append(span)
    scores = {name: round(sum(values) / len(values), 2) if values else None for name, values in buckets.items()}
    evaluation_id = results[0].get("evaluation_id") if results else None
    if evaluation_id:
        async def mark_aggregating() -> None:
            async with async_session_factory() as db:
                evaluation = await db.get(Evaluation, evaluation_id)
                if evaluation and evaluation.status == EvaluationStatus.RUNNING.value:
                    transition(evaluation, EvaluationStatus.AGGREGATING, EVALUATION_TRANSITIONS)
                    await db.commit()
        _run(mark_aggregating())
    base = {
        "evaluation_id": evaluation_id,
        "trace": {"trace_id": evaluation_id or "", "spans": combined_spans},
        "dimensions": scores,
        "case_summary": {
            "total": len(results),
            "completed": sum(item.get("status") == "completed" for item in results),
            "failed": sum(item.get("status") == "failed" for item in results),
            "needs_review": sum(item.get("status") == "needs_review" for item in results),
        },
        "unknown_weight_ratio": round(sum(unknown_ratios) / len(unknown_ratios), 4) if unknown_ratios else 0.0,
        "critical_security_failure": critical_failure,
    }
    if any(value is None for value in scores.values()) or base["unknown_weight_ratio"] > 0.15:
        return {**base, "status": "needs_review"}
    aggregate = aggregate_score(scores, horizon)
    if critical_failure:
        aggregate["overall_score"] = min(float(aggregate["overall_score"]), 59.0)
        aggregate["grade"] = "D"
    return {**base, "status": "completed", **aggregate}


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
        target = EvaluationStatus.COMPLETED if result["status"] == "completed" else EvaluationStatus.NEEDS_REVIEW
        if evaluation.status == EvaluationStatus.AGGREGATING.value:
            transition(evaluation, target, EVALUATION_TRANSITIONS)
        else:
            evaluation.status = target.value
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
    await APIKeyVault.purge(evaluation_id)
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


def build_evaluation_dag(
    submission_id: str,
    evaluation_id: str,
    horizon: str,
    case_ids: list[str],
):
    """Build the only supported evaluation workflow: one task per snapshotted Case."""
    if not evaluation_id:
        raise ValueError("evaluation_id is required")
    if not case_ids:
        raise ValueError("at least one evaluation Case is required")
    cases = group(run_evaluation_case.si(submission_id, evaluation_id, case_id) for case_id in case_ids)
    return chain(
        validate_submission.si(submission_id, evaluation_id),
        chord(cases, aggregate_case_results.s(horizon)),
        finalize_evaluation.s(),
    )
