import pytest

from app.engine.attribution import Attribution, AttributionType
from app.engine.self_eval_loop import AutoCorrector, SelfEvalLoop, check_degradation


def attribution(kind):
    return Attribution(type=kind, dimension="trajectory", metric="tool", score=40, confidence=1, finding="bad", suggestion="fix")


def test_corrections_only_auto_apply_supported_types():
    corrector = AutoCorrector()
    tool = corrector.apply_correction(attribution(AttributionType.TOOL_CALL_ERROR), {})
    assert tool.applied and tool.config["tool_policy"]["validate_arguments"]
    skill = corrector.apply_correction(attribution(AttributionType.SKILL_DEFECT), {})
    assert not skill.applied and skill.requires_human


def test_degradation_detects_old_pass_becoming_failure_or_missing():
    result = check_degradation({"A": "Yes", "B": "No", "C": "Yes"}, {"A": "No", "B": "Yes"})
    assert not result["passed"]
    assert result["degraded"] == ["A"]
    assert result["improved"] == ["B"]
    assert result["missing"] == ["C"]


@pytest.mark.asyncio
async def test_loop_applies_correction_and_passes_full_rerun():
    async def evaluate(config):
        fixed = config.get("tool_policy", {}).get("validate_arguments", False)
        return {"score": 100 if fixed else 50, "rubrics": {"R1": "Yes", "R2": "Yes" if fixed else "No"}}
    loop = SelfEvalLoop(max_retries=2)
    result = await loop.run({}, evaluate, lambda evaluation: [attribution(AttributionType.TOOL_CALL_ERROR)])
    assert result["status"] == "passed"
    assert len(result["attempts"]) == 2


@pytest.mark.asyncio
async def test_loop_rolls_back_on_degradation():
    calls = 0
    async def evaluate(config):
        nonlocal calls
        calls += 1
        return {"score": 50, "rubrics": {"old": "Yes" if calls == 1 else "No", "new": "No"}}
    result = await SelfEvalLoop(max_retries=2).run({}, evaluate, lambda evaluation: [attribution(AttributionType.PLANNING_ERROR)])
    assert result["status"] == "needs_human_intervention"
    assert result["attempts"][-1]["rolled_back"]
