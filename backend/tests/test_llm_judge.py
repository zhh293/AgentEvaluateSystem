import json

import pytest

from app.engine.llm_judge import AIJudge, JudgeResult, dual_judge_rubric
from app.engine.rubric_ai_generator import AIRubricGenerator
from app.engine.trajectory_eval import preprocess_trajectory
from app.schemas.internal.rubric import RubricVerdict
from app.services.alignment_service import compute_human_machine_alignment, deterministic_review_sample


class Transport:
    def __init__(self, payload):
        self.payload = payload

    async def complete(self, prompt):
        return json.dumps(self.payload, ensure_ascii=False)


def span_context():
    return preprocess_trajectory({"trace_id": "x", "spans": [{"span_id": "s1", "span_type": "LLM_CALL", "output": "helpful"}]}).spans


def judge(score, verdict="Yes", evidence="s1", model="judge"):
    return AIJudge(model, transport=Transport({"verdict": verdict, "score": score, "reasoning": "based on evidence", "evidence": [{"span_id": evidence, "quote": "helpful"}]}))


@pytest.mark.asyncio
async def test_single_judge_validates_evidence():
    result = await judge(5).judge_rubric({"description": "helpful", "pass_condition": "pass"}, span_context())
    assert result.score == 5
    with pytest.raises(ValueError, match="不存在"):
        await judge(5, evidence="invented").judge_rubric({"description": "x"}, span_context())


@pytest.mark.asyncio
async def test_dual_judge_agreement_averages():
    result = await dual_judge_rubric({"id": "R1", "description": "x"}, span_context(), judge(4), judge(5))
    assert result.final_score == 4.5
    assert result.final_verdict == RubricVerdict.YES
    assert not result.arbitrated


@pytest.mark.asyncio
async def test_dual_judge_moderate_difference_arbitrates():
    result = await dual_judge_rubric({"id": "R2", "description": "x"}, span_context(), judge(2, "No"), judge(4), judge(3, "Unknown"))
    assert result.final_score == 3
    assert result.arbitrated
    assert result.judge_c is not None


@pytest.mark.asyncio
async def test_large_disagreement_requires_human_review():
    result = await dual_judge_rubric({"id": "R3", "description": "x"}, span_context(), judge(1, "No"), judge(5))
    assert result.final_score is None
    assert result.needs_human_review


def test_alignment_threshold_and_deterministic_sampling():
    async def create():
        return await dual_judge_rubric({"id": "R1", "description": "x"}, span_context(), judge(4), judge(5))
    import asyncio
    result = asyncio.run(create())
    alignment = compute_human_machine_alignment([result], [{"rubric_id": "R1", "verdict": "Yes"}])
    assert alignment["alignment_percent"] == 100
    assert alignment["automation_allowed"]
    items = [{"rubric_id": str(index)} for index in range(20)]
    assert deterministic_review_sample(items, "eval") == deterministic_review_sample(items, "eval")
    assert len(deterministic_review_sample(items, "eval")) == 2


@pytest.mark.asyncio
async def test_ai_rubric_generation_parses_and_validates():
    raw = [
        {"description": f"场景检查项 {index}", "dimension": "result" if index < 4 else "trajectory", "check_type": "llm_judge", "verdict_type": "binary", "pass_condition": f"第 {index} 项要求全部满足", "weight": 1.0}
        for index in range(8)
    ]
    rubrics = await AIRubricGenerator(Transport({"rubrics": raw})).generate_from_description("task")
    assert len(rubrics) == 8
    assert all(item.source.value == "ai_gen" for item in rubrics)
