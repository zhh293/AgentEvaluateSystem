from __future__ import annotations

import json
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from app.engine.efficiency_eval import evaluate_efficiency
from app.engine.rubric_evaluator import evaluate_rubric
from app.engine.security_eval import evaluate_security
from app.engine.trajectory_eval import (
    compute_trajectory_stats, evaluate_long_horizon_trajectory,
    evaluate_short_horizon_trajectory, preprocess_trajectory,
)
from app.infrastructure.database import async_session_factory
from app.models.case_set import EvaluationCase, ExecutionAttempt
from app.models.artifact import Artifact
from app.models.submission import Submission
from app.services.agent_package import contract_from_dict
from app.services.agent_runtime import get_agent_image_runtime
from app.services.api_key_vault import APIKeyVault
from app.infrastructure.minio import minio_client
from app.services.evidence_security import redact_evidence
from sqlalchemy import func, select


async def execute_evaluation_case(submission_id: str, evaluation_id: str, evaluation_case_id: str) -> dict[str, Any]:
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        case = (await db.execute(
            select(EvaluationCase).where(EvaluationCase.id == evaluation_case_id).with_for_update()
        )).scalar_one_or_none()
        if submission is None or case is None or str(case.evaluation_id) != evaluation_id:
            raise LookupError("Submission 或 EvaluationCase 不存在")
        if case.status in {"completed", "needs_review"} and case.result:
            cached = dict(case.result)
            return {
                "case_id": case.case_key, "status": case.status,
                "dimensions": dict(case.dimension_scores or {}),
                "unknown_weight_ratio": float(case.unknown_weight or 0),
                "critical_failure": bool(cached.get("critical_failure")),
                "rubric_results": cached.get("rubric_results", []),
                "agent_result": cached.get("agent_result"), "trace": {"spans": []},
                "cache_hit": True,
            }
        config = dict(submission.config or {})
        attempt_number = int((await db.execute(
            select(func.coalesce(func.max(ExecutionAttempt.attempt_number), 0))
            .where(ExecutionAttempt.evaluation_case_id == case.id)
        )).scalar_one()) + 1
        attempt = ExecutionAttempt(
            evaluation_case_id=case.id, attempt_number=attempt_number, status="running",
        )
        db.add(attempt)
        await db.flush()
        attempt_id = str(attempt.id)
        case.status = "running"
        case.started_at = datetime.now(timezone.utc)
        await db.commit()
        image_ref, risk_level = submission.image_ref, submission.risk_level
    if not image_ref:
        raise RuntimeError("Submission 镜像尚未 ready")
    api_key = await APIKeyVault.retrieve(evaluation_id)
    if not api_key:
        raise RuntimeError("运行时模型凭据不存在或已过期")
    runtime_config = config.get("runtime_config") or {}
    public_env = ((runtime_config.get("environment") or {}).get("public") or {})
    environment = {
        **{str(key): str(value) for key, value in public_env.items()},
        "LLM_API_BASE": str(config.get("llm_api_base", "")),
        "LLM_MODEL": str(config.get("llm_model", "")),
        "AGENTEVAL_EVALUATION_ID": evaluation_id,
        "AGENTEVAL_CASE_ID": case.case_key,
        "AGENTEVAL_ATTEMPT_ID": attempt_id,
    }
    bindings = ((runtime_config.get("environment") or {}).get("secret_refs") or [])
    for binding in bindings:
        if binding.get("source") == "evaluation.llm_api_key":
            environment[str(binding["target"])] = api_key
    invocation = dict(case.invocation)
    execution = await get_agent_image_runtime().execute(
        evaluation_id=f"{evaluation_id}-{attempt_id[:8]}", image=image_ref,
        contract=contract_from_dict(config["package_contract"]),
        task={"case_id": case.case_key}, invocation=invocation,
        environment=environment, risk_level=risk_level,
        service_images=dict(config.get("service_images") or {}),
    )
    safe_result = redact_evidence(execution.result, (api_key,))
    safe_trace = redact_evidence(execution.trace, (api_key,))
    safe_trace.setdefault("spans", []).append({
        "span_id": "platform-result-evidence",
        "parent_span_id": None,
        "span_type": "AGENT_EXECUTION",
        "operation": "case_result",
        "status": "ok",
        "output": {"result": safe_result, "http": safe_result.get("http", {}), "cli": safe_result.get("cli", {})},
        "attributes": {"agenteval.case_id": case.case_key, "agenteval.attempt_id": attempt_id},
    })
    trajectory = preprocess_trajectory(safe_trace)
    evidence = {
        "result": safe_result,
        "http": safe_result.get("http", {}),
        "cli": safe_result.get("cli", {}),
        "output": safe_result.get("output"),
        "trace": safe_trace,
    }
    rubric_results = [
        await evaluate_rubric(rubric, evidence, trajectory.spans)
        for rubric in list(case.rubrics)
    ]
    rubric_scores: dict[str, list[tuple[float, float]]] = {}
    unknown_weight = 0.0
    total_weight = 0.0
    for result in rubric_results:
        total_weight += result.weight
        if result.score is None:
            unknown_weight += result.weight
        else:
            rubric_scores.setdefault(result.dimension, []).append((result.score, result.weight))
    dimensions = {
        name: round(sum(score * weight for score, weight in values) / sum(weight for _, weight in values), 2)
        for name, values in rubric_scores.items() if values
    }
    declared_tools = list(config.get("enabled_tools", []))
    if submission.horizon == "long":
        trajectory_metrics = evaluate_long_horizon_trajectory(trajectory, declared_tools)
    else:
        trajectory_metrics = evaluate_short_horizon_trajectory(trajectory, declared_tools, None)
    if "trajectory" not in dimensions:
        dimensions["trajectory"] = _metric_mean(trajectory_metrics)
    stats = compute_trajectory_stats(trajectory)
    efficiency = evaluate_efficiency(stats, config.get("cost_config", {}), config.get("baseline"))
    if "efficiency" not in dimensions:
        dimensions["efficiency"] = round(mean([efficiency["step_efficiency"], efficiency["token_efficiency"]]), 2)
    security = evaluate_security(trajectory, config)
    if "security" not in dimensions:
        dimensions["security"] = _metric_mean(security)
    result_payload = {
        "case_id": case.case_key, "status": "completed",
        "dimensions": dimensions,
        "unknown_weight_ratio": 0.0 if not total_weight else round(unknown_weight / total_weight, 4),
        "critical_failure": any(item.critical and item.verdict == "fail" for item in rubric_results),
        "rubric_results": [asdict(item) for item in rubric_results],
        "trace": safe_trace,
        "agent_result": safe_result,
        "metrics": {"trajectory": trajectory_metrics, "efficiency": efficiency, "security": security},
    }
    async with async_session_factory() as db:
        case = await db.get(EvaluationCase, evaluation_case_id)
        trace_bytes = json.dumps(safe_trace, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        trace_path, trace_digest = await asyncio.to_thread(
            minio_client.upload_bytes,
            f"evaluations/{evaluation_id}/cases/{case.case_key}/trace.json",
            trace_bytes, "application/json",
        )
        trace_artifact = Artifact(
            owner_type="evaluation_case", owner_id=case.id, artifact_type="raw_trace",
            storage_path=trace_path, sha256=trace_digest, media_type="application/json",
            size_bytes=len(trace_bytes), schema_version="1",
            metadata_json={"case_key": case.case_key, "redacted": True},
        )
        db.add(trace_artifact)
        await db.flush()
        case.trace_artifact_id = trace_artifact.id
        attempt = await db.get(ExecutionAttempt, attempt_id)
        attempt.status = "completed"
        attempt.result = {key: value for key, value in result_payload.items() if key != "trace"}
        attempt.trace_artifact_id = trace_artifact.id
        attempt.completed_at = datetime.now(timezone.utc)
        case.status = "completed" if result_payload["unknown_weight_ratio"] == 0 else "needs_review"
        case.result = {**{key: value for key, value in result_payload.items() if key != "trace"}, "trace_storage_path": trace_path}
        case.dimension_scores = dimensions
        case.unknown_weight = str(result_payload["unknown_weight_ratio"])
        case.completed_at = datetime.now(timezone.utc)
        await db.commit()
    return result_payload


def _metric_mean(payload: dict[str, Any]) -> float | None:
    values = [float(value["score"]) for value in payload.values() if isinstance(value, dict) and isinstance(value.get("score"), (int, float))]
    return round(mean(values), 2) if values else None
