from app.engine.trajectory_eval import (
    compute_trajectory_stats,
    evaluate_long_horizon_trajectory,
    evaluate_short_horizon_trajectory,
    preprocess_trajectory,
)


def sample_trace():
    return {
        "trace_id": "trace-1",
        "spans": [
            {"span_id": "root", "span_type": "AGENT_EXECUTION", "started_ns": 1, "ended_ns": 101, "duration_ms": 0.0001},
            {"span_id": "plan", "parent_span_id": "root", "span_type": "AGENT_PLANNING", "started_ns": 2, "ended_ns": 3, "output": {"steps": ["search"]}},
            {"span_id": "a", "parent_span_id": "root", "span_type": "TOOL_EXECUTION", "operation": "search", "started_ns": 4, "ended_ns": 5, "status": "error", "attributes": {"tool.name": "search", "tool.arguments": {"q": "x"}}},
            {"span_id": "b", "parent_span_id": "root", "span_type": "TOOL_EXECUTION", "operation": "search", "started_ns": 6, "ended_ns": 7, "status": "ok", "attributes": {"tool.name": "search", "tool.arguments": {"q": "x"}}},
            {"span_id": "c", "parent_span_id": "root", "span_type": "TOOL_EXECUTION", "operation": "invented", "started_ns": 8, "ended_ns": 9, "attributes": {"tool.name": "invented"}},
            {"span_id": "llm", "parent_span_id": "root", "span_type": "LLM_CALL", "started_ns": 10, "ended_ns": 20, "attributes": {"gen_ai.usage.input_tokens": 10, "gen_ai.usage.output_tokens": 5, "gen_ai.usage.total_tokens": 15}},
            {"span_id": "ignored", "span_type": "HTTP_INTERNAL", "started_ns": 0},
        ],
    }


def test_preprocessing_filters_unknown_and_orders_spans():
    trajectory = preprocess_trajectory(sample_trace())
    assert len(trajectory.spans) == 6
    assert trajectory.spans[0].span_id == "root"
    assert trajectory.root_span_id == "root"


def test_stats_and_short_metrics():
    trajectory = preprocess_trajectory(sample_trace())
    stats = compute_trajectory_stats(trajectory)
    assert stats["tool_calls"] == 3
    assert stats["llm_calls"] == 1
    assert stats["total_tokens"] == 15
    result = evaluate_short_horizon_trajectory(trajectory, ["search"])
    assert result["tool_selection_accuracy"]["score"] < 100
    assert result["step_efficiency"]["redundant_steps"] == 1


def test_long_metrics_detect_recovery_and_hallucination():
    result = evaluate_long_horizon_trajectory(preprocess_trajectory(sample_trace()), ["search"])
    assert result["error_recovery_rate"]["score"] == 100
    assert result["hallucination_rate"]["hallucinated_calls"] == 1
    assert result["plan_quality"]["score"] == 100
