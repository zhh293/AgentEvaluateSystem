"""Trace normalization and deterministic trajectory metrics."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from app.schemas.internal.trace import SpanData, SpanType, TrajectoryData


def preprocess_trajectory(raw_trace: dict) -> TrajectoryData:
    raw_spans = raw_trace.get("spans", [])
    spans = []
    for raw in raw_spans:
        span_type = raw.get("span_type") or raw.get("operation")
        try:
            typed = SpanType(span_type)
        except (ValueError, TypeError):
            # Unknown OTel infrastructure spans are irrelevant to Agent metrics.
            continue
        attributes = raw.get("attributes") or {}
        spans.append(
            SpanData(
                span_id=str(raw.get("span_id", "")),
                parent_span_id=raw.get("parent_span_id"),
                span_type=typed,
                operation=str(raw.get("operation", span_type)),
                start_time=raw.get("start_time"),
                end_time=raw.get("end_time"),
                started_ns=raw.get("started_ns"),
                ended_ns=raw.get("ended_ns"),
                duration_ms=float(raw.get("duration_ms", 0) or 0),
                status=str(raw.get("status", "ok")),
                input=raw.get("input"),
                output=raw.get("output"),
                attributes=attributes,
                tokens=int(raw.get("tokens", attributes.get("gen_ai.usage.total_tokens", 0)) or 0),
                error=raw.get("error") or raw.get("error.type"),
            )
        )
    spans.sort(key=lambda item: item.started_ns or int(item.start_time.timestamp() * 1e9) if item.start_time else 0)
    roots = [span for span in spans if not span.parent_span_id]
    duration = float(raw_trace.get("total_duration_ms", 0) or 0)
    if not duration and spans:
        starts = [span.started_ns for span in spans if span.started_ns is not None]
        ends = [span.ended_ns for span in spans if span.ended_ns is not None]
        if starts and ends:
            duration = (max(ends) - min(starts)) / 1_000_000
        else:
            duration = sum(span.duration_ms for span in spans)
    return TrajectoryData(
        trace_id=str(raw_trace.get("trace_id", "")),
        root_span_id=str(raw_trace.get("root_span_id") or (roots[0].span_id if roots else "")),
        spans=spans,
        environment_snapshots=raw_trace.get("environment_snapshots", []),
        metadata=raw_trace.get("metadata", {}),
        total_duration_ms=duration,
    )


def filter_spans_by_type(trajectory: TrajectoryData, span_types: list[SpanType]) -> list[SpanData]:
    wanted = set(span_types)
    return [span for span in trajectory.spans if span.span_type in wanted]


def extract_rubric_context(trajectory: TrajectoryData, rubric: dict) -> list[SpanData]:
    mapping = {
        "result": [SpanType.AGENT_EXECUTION, SpanType.LLM_CALL],
        "trajectory": [SpanType.AGENT_PLANNING, SpanType.AGENT_DECISION, SpanType.TOOL_EXECUTION, SpanType.SKILL_EXECUTION],
        "efficiency": list(SpanType),
        "security": [SpanType.TOOL_EXECUTION, SpanType.EXTERNAL_API, SpanType.ENVIRONMENT_STATE_CHANGE],
    }
    return filter_spans_by_type(trajectory, mapping.get(str(rubric.get("dimension", "")), list(SpanType)))


def compute_trajectory_stats(trajectory: TrajectoryData) -> dict:
    tools = filter_spans_by_type(trajectory, [SpanType.TOOL_EXECUTION])
    llms = filter_spans_by_type(trajectory, [SpanType.LLM_CALL])
    durations = sorted(span.duration_ms for span in trajectory.spans)
    return {
        "total_steps": len(trajectory.spans),
        "tool_calls": len(tools),
        "llm_calls": len(llms),
        "errors": sum(span.status == "error" or bool(span.error) for span in trajectory.spans),
        "total_tokens": sum(span.tokens for span in trajectory.spans),
        "input_tokens": sum(int(span.attributes.get("gen_ai.usage.input_tokens", 0) or 0) for span in llms),
        "output_tokens": sum(int(span.attributes.get("gen_ai.usage.output_tokens", 0) or 0) for span in llms),
        "total_duration_ms": trajectory.total_duration_ms,
        "span_durations_ms": durations,
    }


def _tool_name(span: SpanData) -> str:
    return str(span.attributes.get("tool.name") or span.attributes.get("name") or span.operation or "")


def _tool_args(span: SpanData) -> dict:
    value = span.attributes.get("tool.arguments", span.input or {})
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def evaluate_tool_selection(trajectory: TrajectoryData, declared_tools: list[str]) -> dict:
    calls = filter_spans_by_type(trajectory, [SpanType.TOOL_EXECUTION])
    if not calls:
        return {"score": 100.0, "calls": 0, "undeclared": []}
    declared = set(declared_tools)
    undeclared = sorted({_tool_name(span) for span in calls if _tool_name(span) not in declared})
    valid = sum(_tool_name(span) in declared for span in calls)
    return {"score": round(100 * valid / len(calls), 2), "calls": len(calls), "undeclared": undeclared}


def evaluate_tool_parameters(trajectory: TrajectoryData) -> dict:
    calls = filter_spans_by_type(trajectory, [SpanType.TOOL_EXECUTION])
    if not calls:
        return {"score": 100.0, "invalid_calls": 0, "calls": 0}
    invalid = 0
    for span in calls:
        attributes = span.attributes
        schema_valid = attributes.get("tool.schema_valid")
        if schema_valid is False or span.status == "error" and attributes.get("error.type") == "validation":
            invalid += 1
    return {"score": round(100 * (len(calls) - invalid) / len(calls), 2), "invalid_calls": invalid, "calls": len(calls)}


def evaluate_step_redundancy(trajectory: TrajectoryData) -> dict:
    calls = filter_spans_by_type(trajectory, [SpanType.TOOL_EXECUTION])
    redundant = 0
    for previous, current in zip(calls, calls[1:]):
        if _tool_name(previous) == _tool_name(current) and _tool_args(previous) == _tool_args(current):
            redundant += 1
    score = 100 if not calls else 100 * (1 - redundant / len(calls))
    return {"score": round(score, 2), "redundant_steps": redundant, "tool_calls": len(calls)}


def evaluate_error_recovery(trajectory: TrajectoryData) -> dict:
    errors = [index for index, span in enumerate(trajectory.spans) if span.status == "error" or span.error]
    recovered = 0
    for index in errors:
        failed = trajectory.spans[index]
        later = trajectory.spans[index + 1 :]
        if any(span.status == "ok" and (span.parent_span_id == failed.parent_span_id or _tool_name(span) == _tool_name(failed)) for span in later):
            recovered += 1
    return {"score": 100.0 if not errors else round(100 * recovered / len(errors), 2), "errors": len(errors), "recovered": recovered}


def evaluate_hallucination(trajectory: TrajectoryData, available_tools: list[str]) -> dict:
    selection = evaluate_tool_selection(trajectory, available_tools)
    calls = selection["calls"]
    hallucinated = sum(1 for span in filter_spans_by_type(trajectory, [SpanType.TOOL_EXECUTION]) if _tool_name(span) not in set(available_tools))
    return {"score": 100.0 if not calls else round(100 * (1 - hallucinated / calls), 2), "hallucinated_calls": hallucinated, "calls": calls}


def evaluate_plan_quality(trajectory: TrajectoryData) -> dict:
    plans = filter_spans_by_type(trajectory, [SpanType.AGENT_PLANNING])
    if not plans:
        return {"score": None, "judge_type": "pending_llm", "details": {"planning_spans": 0}}
    structured = sum(bool(span.attributes.get("plan.steps") or span.output) for span in plans)
    return {"score": round(100 * structured / len(plans), 2), "judge_type": "structural", "details": {"planning_spans": len(plans)}}


def evaluate_short_horizon_trajectory(trajectory: TrajectoryData, declared_tools: list[str], expected_tool_chain: list[str] | None = None) -> dict:
    selection = evaluate_tool_selection(trajectory, declared_tools)
    if expected_tool_chain is not None:
        actual = [_tool_name(span) for span in filter_spans_by_type(trajectory, [SpanType.TOOL_EXECUTION])]
        selection["expected_chain_match"] = actual == expected_tool_chain
    return {"tool_selection_accuracy": selection, "tool_call_correctness": evaluate_tool_parameters(trajectory), "step_efficiency": evaluate_step_redundancy(trajectory)}


def evaluate_long_horizon_trajectory(trajectory: TrajectoryData, available_tools: list[str]) -> dict:
    return {
        "plan_quality": evaluate_plan_quality(trajectory),
        "tool_selection_accuracy": evaluate_tool_selection(trajectory, available_tools),
        "tool_parameter_correctness": evaluate_tool_parameters(trajectory),
        "error_recovery_rate": evaluate_error_recovery(trajectory),
        "hallucination_rate": evaluate_hallucination(trajectory, available_tools),
        "step_redundancy": evaluate_step_redundancy(trajectory),
    }
