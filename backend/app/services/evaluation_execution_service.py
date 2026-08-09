"""Worker-side execution that joins storage, sandboxing and four evaluators."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from app.engine.efficiency_eval import evaluate_efficiency
from app.engine.result_eval import evaluate_long_horizon, evaluate_short_horizon
from app.engine.security_eval import evaluate_security
from app.engine.trajectory_eval import (
    compute_trajectory_stats,
    evaluate_long_horizon_trajectory,
    evaluate_short_horizon_trajectory,
    preprocess_trajectory,
)
from app.infrastructure.database import async_session_factory
from app.infrastructure.minio import minio_client
from app.models.submission import Submission
from app.services.api_key_vault import APIKeyVault
from app.services.sandbox_service import get_sandbox_manager
from app.services.submission_service import _extract_package


def _scores(payload: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for value in payload.values():
        if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
            values.append(float(value["score"]))
    return values


def dimension_score(payload: dict[str, Any]) -> float | None:
    values = _scores(payload)
    return round(mean(values), 2) if values else None


async def execute_submission(submission_id: str, evaluation_id: str) -> dict[str, Any]:
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        if submission is None:
            raise LookupError(f"Submission {submission_id} 不存在")
        config = dict(submission.config or {})
        package = minio_client.get_package(submission.source_package_path)

    filename = Path(submission.source_package_path).name
    # Object paths normalize the filename to package.ext; retain the original
    # archive type through that extension.
    source_dir = _extract_package(package, filename)
    manager = get_sandbox_manager()
    container_id: str | None = None
    try:
        task = config.get("evaluation_task") or {
            "id": evaluation_id,
            "input": config.get("evaluation_input", config.get("description", "")),
        }
        (source_dir / "task.json").write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
        api_key = await APIKeyVault.retrieve_and_purge(submission_id)
        environment = {"LLM_API_KEY": api_key} if api_key else {}
        image = manager.image_for_risk(submission.risk_level)
        container_id = await manager.create_sandbox(
            evaluation_id,
            image,
            str(source_dir),
            timeout=int(config.get("max_execution_time_seconds", 300)),
            environment=environment,
            network_enabled=bool(config.get("allowed_domains")),
            writable=submission.risk_level == "medium",
        )
        exit_code, _, stderr = await manager.run_agent(
            container_id,
            timeout=int(config.get("max_execution_time_seconds", 300)),
        )
        result_code, result_json, result_error = await manager.execute_in_sandbox(
            container_id, ["cat", "/tmp/result.json"], timeout=10
        )
        trace_code, trace_json, trace_error = await manager.execute_in_sandbox(
            container_id, ["cat", "/tmp/trace.json"], timeout=10
        )
        if result_code or trace_code:
            raise RuntimeError(result_error or trace_error or stderr or "沙箱未生成评测产物")
        result = json.loads(result_json)
        raw_trace = json.loads(trace_json)
        if exit_code or result.get("status") != "success":
            raise RuntimeError(str(result.get("error") or stderr or "Agent 执行失败"))
    finally:
        if container_id:
            await manager.destroy_sandbox(container_id)
        shutil.rmtree(source_dir, ignore_errors=True)

    trajectory = preprocess_trajectory(raw_trace)
    output = result.get("output")
    answer = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)
    declared_tools = list(config.get("enabled_tools", []))
    if submission.horizon == "long":
        expected = config.get("expected_behavior", {})
        result_metrics = evaluate_long_horizon(output if isinstance(output, dict) else {"output": output}, expected, result)
        trajectory_metrics = evaluate_long_horizon_trajectory(trajectory, declared_tools)
    else:
        result_metrics = evaluate_short_horizon(
            answer,
            config.get("ground_truth"),
            str(task.get("input", "")),
            config,
        )
        trajectory_metrics = evaluate_short_horizon_trajectory(
            trajectory, declared_tools, config.get("expected_tool_chain")
        )
    stats = compute_trajectory_stats(trajectory)
    stats["minimum_steps"] = config.get("minimum_steps", stats.get("total_steps", 0))
    efficiency_metrics = evaluate_efficiency(stats, config.get("cost_config", {}), config.get("baseline"))
    security_metrics = evaluate_security(trajectory, config)
    return {
        "submission_id": submission_id,
        "evaluation_id": evaluation_id,
        "stage": "evaluated",
        "evaluation_inputs": {
            "result": {"score": dimension_score(result_metrics), "details": result_metrics},
            "trajectory": {"score": dimension_score(trajectory_metrics), "details": trajectory_metrics},
            "efficiency": {
                "score": round(mean([efficiency_metrics["step_efficiency"], efficiency_metrics["token_efficiency"]]), 2),
                "details": efficiency_metrics,
            },
            "security": {"score": dimension_score(security_metrics), "details": security_metrics},
        },
        "trace": raw_trace,
        "agent_result": result,
    }
