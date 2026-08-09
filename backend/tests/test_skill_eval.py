import pytest

from app.engine.skill_eval import evaluate_single_skill, evaluate_skill_integration


@pytest.mark.asyncio
async def test_single_skill_requires_ninety_percent():
    async def executor(case):
        return {"status": "success", "output": case["expected"], "duration_ms": case["id"], "tokens": 2}
    cases = [{"id": index, "expected": index} for index in range(10)]
    result = await evaluate_single_skill("echo", {}, cases, executor)
    assert result["score"] == 100
    assert result["passed"]
    assert result["total_tokens"] == 20


def test_n_plus_one_detects_case_regression_and_tool_conflict():
    result = evaluate_skill_integration(
        {"a": 100, "b": 80}, {"a": 100, "b": 100}, ["search"], {"old": ["search"]}
    )
    assert not result["passed"]
    assert result["regressions"][0]["case_id"] == "b"
    assert result["tool_conflicts"]
