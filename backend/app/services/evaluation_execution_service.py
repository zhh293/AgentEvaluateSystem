"""Worker-side execution joining built Agent images and evaluators."""

from __future__ import annotations

import json
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
from app.models.submission import Submission
from app.services.agent_package import contract_from_dict
from app.services.agent_runtime import get_agent_image_runtime
from app.services.api_key_vault import APIKeyVault


def _scores(payload: dict[str, Any]) -> list[float]:
    return [float(value["score"]) for value in payload.values() if isinstance(value, dict) and isinstance(value.get("score"), (int, float))]


def dimension_score(payload: dict[str, Any]) -> float | None:
    values = _scores(payload)
    return round(mean(values), 2) if values else None


def build_invocation_envelope(evaluation_id: str, raw_task: dict[str, Any], config: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Project only public task constraints into the untrusted Agent request."""
    return {
        "protocol_version": "1.0",
        "evaluation_id": evaluation_id,
        "case_id": str(raw_task.get("id", evaluation_id)),
        "task": raw_task,
        "guidance": {
            "language": config.get("language"),
            "output_format": config.get("output_format"),
            "max_output_chars": config.get("max_output_chars"),
        },
        "runtime": {"deadline_seconds": timeout, "trace_level": "tool_calls"},
    }


async def execute_submission(submission_id: str, evaluation_id: str) -> dict[str, Any]:
    async with async_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        if submission is None:
            raise LookupError(f"Submission {submission_id} 不存在")
        config = dict(submission.config or {})
        image_ref = submission.image_ref
        horizon = submission.horizon
        risk_level = submission.risk_level
    if not image_ref:
        raise RuntimeError("Submission 镜像尚未构建完成")

    raw_task = config.get("evaluation_task") or {
        "id": evaluation_id,
        "input": config.get("evaluation_input", config.get("description", "")),
    }
    # The invocation protocol deliberately excludes generated/private Rubrics.
    # Rubrics stay in platform configuration and are consumed by evaluators
    # after the untrusted Agent returns. Only explicit user-visible constraints
    # are projected into `guidance`.
    task = build_invocation_envelope(
        evaluation_id, raw_task, config, contract_from_dict(config["package_contract"]).runtime.timeout_seconds
    )
    api_key = await APIKeyVault.retrieve_and_purge(evaluation_id)
    if not api_key:
        raise RuntimeError("运行时模型凭据不存在或已过期，请重新提交 Agent")
    provider = str(config.get("llm_provider", "")).lower()
    environment = {
        "LLM_API_KEY": api_key,
        "LLM_API_BASE": str(config.get("llm_api_base", "")),
        "LLM_MODEL": str(config.get("llm_model", "")),
    }
    provider_key_names = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "zhipu": "ZHIPUAI_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
    }
    if provider in provider_key_names:
        environment[provider_key_names[provider]] = api_key
    if provider == "openai":
        environment["OPENAI_BASE_URL"] = environment["LLM_API_BASE"]
    execution = await get_agent_image_runtime().execute(
        evaluation_id=evaluation_id,
        image=image_ref,
        contract=contract_from_dict(config["package_contract"]),
        task=task,
        environment=environment,
        risk_level=risk_level,
        service_images=dict(config.get("service_images") or {}),
    )
    result = execution.result
    raw_trace = execution.trace
    if result.get("status", "success") != "success":
        raise RuntimeError(str(result.get("error") or "Agent 执行失败"))

    trajectory = preprocess_trajectory(raw_trace)
    output = result.get("output")
    answer = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)
    declared_tools = list(config.get("enabled_tools", []))
    if horizon == "long":
        expected = config.get("expected_behavior", {})
        result_metrics = evaluate_long_horizon(output if isinstance(output, dict) else {"output": output}, expected, result)
        trajectory_metrics = evaluate_long_horizon_trajectory(trajectory, declared_tools)
    else:
        result_metrics = evaluate_short_horizon(answer, config.get("ground_truth"), str(raw_task.get("input", "")), config)
        trajectory_metrics = evaluate_short_horizon_trajectory(trajectory, declared_tools, config.get("expected_tool_chain"))
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
            "efficiency": {"score": round(mean([efficiency_metrics["step_efficiency"], efficiency_metrics["token_efficiency"]]), 2), "details": efficiency_metrics},
            "security": {"score": dimension_score(security_metrics), "details": security_metrics},
        },
        "trace": raw_trace,
        "agent_result": result,
    }
