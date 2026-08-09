"""Deterministic efficiency and cost calculations."""

from __future__ import annotations

import math
from typing import Iterable


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def compute_step_efficiency(stats: dict) -> float:
    actual = int(stats.get("total_steps", 0) or 0)
    minimum = int(stats.get("minimum_steps", actual or 1) or 1)
    return 100.0 if actual == 0 else round(min(minimum / actual, 1.0) * 100, 2)


def compute_token_efficiency(stats: dict, baseline: dict | None = None) -> float:
    tokens = int(stats.get("total_tokens", 0) or 0)
    complexity = float(stats.get("complexity_coefficient", 1.0) or 1.0)
    normalized = tokens / max(complexity, 0.1)
    target = float((baseline or {}).get("target_tokens", stats.get("target_tokens", normalized or 1)) or 1)
    return 100.0 if normalized == 0 else round(min(target / normalized, 1.0) * 100, 2)


def compute_cost(stats: dict, cost_config: dict) -> float:
    input_tokens = int(stats.get("input_tokens", 0) or 0)
    output_tokens = int(stats.get("output_tokens", 0) or 0)
    unit = float(cost_config.get("token_unit", 1_000_000) or 1_000_000)
    token_cost = input_tokens / unit * float(cost_config.get("input_price", 0) or 0)
    token_cost += output_tokens / unit * float(cost_config.get("output_price", 0) or 0)
    tool_costs = cost_config.get("tool_costs", {}) or {}
    by_tool = stats.get("tool_calls_by_name", {}) or {}
    tool_cost = sum(int(count) * float(tool_costs.get(name, 0) or 0) for name, count in by_tool.items())
    tool_cost += int(stats.get("tool_calls", 0) or 0) * float(cost_config.get("default_tool_call_price", 0) or 0)
    return round(token_cost + tool_cost, 6)


def evaluate_efficiency(trajectory_stats: dict, cost_config: dict, baseline: dict | None = None) -> dict:
    durations = trajectory_stats.get("span_durations_ms", []) or []
    result = {
        "step_efficiency": compute_step_efficiency(trajectory_stats),
        "token_efficiency": compute_token_efficiency(trajectory_stats, baseline),
        "latency_p50_ms": percentile(durations, 0.50),
        "latency_p90_ms": percentile(durations, 0.90),
        "latency_p99_ms": percentile(durations, 0.99),
        "cost_per_task_usd": compute_cost(trajectory_stats, cost_config),
    }
    if baseline:
        result["baseline_comparison"] = {
            "token_ratio": round(trajectory_stats.get("total_tokens", 0) / max(float(baseline.get("p50_tokens", 1) or 1), 1), 3),
            "latency_ratio": round(trajectory_stats.get("total_duration_ms", 0) / max(float(baseline.get("p50_latency_ms", 1) or 1), 1), 3),
        }
    return result
