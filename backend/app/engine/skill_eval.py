"""Skill release gates for isolated and N+1 integration evaluation."""

from __future__ import annotations

import inspect
import statistics
from typing import Any, Awaitable, Callable


async def _execute(executor, case: dict) -> dict:
    value = executor(case)
    return await value if inspect.isawaitable(value) else value


def _case_passed(case: dict, result: dict) -> bool:
    if "passed" in result:
        return bool(result["passed"])
    if result.get("status") != "success":
        return False
    expected = case.get("expected")
    return True if expected is None else result.get("output") == expected


async def evaluate_single_skill(skill_name: str, skill_config: dict, test_suite: list[dict], executor: Callable[[dict], Any]) -> dict:
    if not test_suite:
        raise ValueError("Skill test_suite cannot be empty")
    results = []
    for case in test_suite:
        try:
            execution = await _execute(executor, case)
        except Exception as exc:
            execution = {"status": "error", "error": str(exc), "duration_ms": 0}
        results.append({"case_id": case.get("id"), "passed": _case_passed(case, execution), **execution})
    passed = sum(item["passed"] for item in results)
    latencies = [float(item.get("duration_ms", 0) or 0) for item in results]
    score = round(100 * passed / len(results), 2)
    return {
        "skill_name": skill_name,
        "score": score,
        "passed": score >= 90,
        "pass_threshold": 90,
        "cases_passed": passed,
        "cases_total": len(results),
        "latency_p50_ms": statistics.median(latencies),
        "latency_p99_ms": sorted(latencies)[max(0, int(0.99 * (len(latencies) - 1)))],
        "total_tokens": sum(int(item.get("tokens", 0) or 0) for item in results),
        "results": results,
    }


def evaluate_skill_integration(current_case_scores: dict[str, float], baseline_case_scores: dict[str, float], new_skill_tools: list[str] | None = None, existing_skill_tools: dict[str, list[str]] | None = None) -> dict:
    if not baseline_case_scores:
        raise ValueError("baseline case scores cannot be empty")
    missing = sorted(set(baseline_case_scores) - set(current_case_scores))
    regressions = []
    for case_id, baseline in baseline_case_scores.items():
        current = current_case_scores.get(case_id, 0)
        if current < baseline * 0.95:
            regressions.append({"case_id": case_id, "baseline": baseline, "current": current, "ratio": 0 if baseline == 0 else round(current / baseline, 4)})
    baseline_score = sum(baseline_case_scores.values()) / len(baseline_case_scores)
    current_score = sum(current_case_scores.get(case_id, 0) for case_id in baseline_case_scores) / len(baseline_case_scores)
    conflicts = []
    new_tools = set(new_skill_tools or [])
    for skill, tools in (existing_skill_tools or {}).items():
        overlap = sorted(new_tools & set(tools))
        if overlap:
            conflicts.append({"skill": skill, "tools": overlap})
    ratio = 1.0 if baseline_score == 0 and current_score >= 0 else current_score / baseline_score
    return {
        "baseline_score": round(baseline_score, 2),
        "integration_score": round(current_score, 2),
        "retention_ratio": round(ratio, 4),
        "passed": ratio >= 0.95 and not missing and not regressions,
        "threshold": 0.95,
        "missing_cases": missing,
        "regressions": regressions,
        "tool_conflicts": conflicts,
    }
