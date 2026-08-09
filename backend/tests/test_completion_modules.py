import uuid

import pytest

from app.engine.rubric_health import RubricHealthMonitor
from app.engine.self_eval_loop import SelfEvalLoop
from app.infrastructure.quality_gate import QualityGateEngine
from app.schemas.response.evaluation import EvaluationReport
from app.services.evaluation_execution_service import dimension_score


def test_rubric_health_alerts_below_85_percent():
    result = RubricHealthMonitor().evaluate([("Yes", "Yes")] * 8 + [("Yes", "No")] * 2)
    assert result["agreement_rate"] == 0.8
    assert result["healthy"] is False
    assert result["alert"]


def test_dimension_score_excludes_pending_metrics():
    assert dimension_score({"a": {"score": 100}, "b": {"score": None}, "c": {"score": 50}}) == 75
    assert dimension_score({"pending": {"score": None}}) is None


def test_quality_gate_checks_every_requirement():
    result = QualityGateEngine().check_gate("ops_monitor", {"success_rate": 90, "satisfaction": 3.5})
    assert result["passed"] is False
    assert result["checks"]["success_rate"]["passed"] is True
    assert result["checks"]["satisfaction"]["passed"] is False


def test_evaluation_orm_uuid_response_contract():
    report = EvaluationReport.model_validate({
        "id": uuid.uuid4(), "submission_id": uuid.uuid4(), "status": "completed",
        "agent_type": "short_horizon", "horizon": "short",
        "dimensions": {"result": 90, "trajectory": 80, "efficiency": 70, "security": 100},
    })
    assert isinstance(report.id, uuid.UUID)


@pytest.mark.asyncio
async def test_self_eval_loop_degrades_to_best_attempt():
    loop = SelfEvalLoop(max_retries=0)
    result = await loop.run(
        {},
        lambda _: {"score": 42, "rubrics": {"r1": "No"}},
        lambda _: [],
    )
    assert result["status"] == "needs_human_intervention"
    assert result["best_attempt"]["score"] == 42
