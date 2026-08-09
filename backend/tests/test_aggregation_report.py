from unittest.mock import MagicMock

import pytest

from app.engine.aggregator import aggregate_rubrics, aggregate_score
from app.engine.attribution import AttributionType, analyze_attributions
from app.engine.trajectory_eval import preprocess_trajectory
from app.services.report_service import ReportService, compute_benchmark


def test_short_and_long_weights_differ():
    scores = {"result": 100, "trajectory": 0, "efficiency": 0, "security": 0}
    assert aggregate_score(scores, "short")["overall_score"] == 40
    assert aggregate_score(scores, "long")["overall_score"] == 30


def test_invalid_or_missing_dimensions_are_rejected():
    with pytest.raises(ValueError):
        aggregate_score({"result": 100}, "short")
    with pytest.raises(ValueError):
        aggregate_score({"result": 101, "trajectory": 0, "efficiency": 0, "security": 0}, "short")


def test_unknown_rubrics_are_excluded_from_weighted_score():
    assert aggregate_rubrics([
        {"dimension": "result", "score": 100, "weight": 2},
        {"dimension": "result", "score": 50, "weight": 1},
        {"dimension": "result", "score": None, "weight": 99},
    ])["result"] == 83.33


def test_attribution_uses_failed_tool_span():
    trajectory = preprocess_trajectory({"trace_id": "x", "spans": [{"span_id": "tool-1", "span_type": "TOOL_EXECUTION", "status": "error"}]})
    result = analyze_attributions({"trajectory": {"tool_selection": {"score": 40}}}, trajectory)
    assert result[0].type == AttributionType.TOOL_CALL_ERROR
    assert result[0].evidence_span_ids == ["tool-1"]


def test_report_is_complete_and_storable():
    storage = MagicMock()
    storage.upload_json.return_value = "reports/e/report.json"
    service = ReportService(storage)
    report = service.generate_report(
        evaluation_id="e", submission_id="s", agent_name="agent", agent_type="short_horizon", agent_version="1", horizon="short",
        dimension_scores={"result": 90, "trajectory": 80, "efficiency": 70, "security": 100}, historical_scores=[60, 80, 95], baseline_score=80,
    )
    assert report["overall_score"] == 86
    assert report["grade"] == "A-"
    assert report["benchmark_comparison"]["leaderboard_rank"] == 2
    assert service.store_report("e", report) == "reports/e/report.json"
    storage.upload_json.assert_called_once()
