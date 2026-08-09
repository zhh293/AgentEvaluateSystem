from app.engine.efficiency_eval import compute_cost, evaluate_efficiency, percentile


def test_percentiles_are_interpolated():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([], 0.5) is None


def test_cost_uses_per_million_prices_and_tools():
    cost = compute_cost(
        {"input_tokens": 1_000_000, "output_tokens": 500_000, "tool_calls_by_name": {"search": 2}},
        {"input_price": 2, "output_price": 4, "tool_costs": {"search": 0.01}},
    )
    assert cost == 4.02


def test_efficiency_includes_latency_and_baseline():
    result = evaluate_efficiency(
        {"total_steps": 10, "minimum_steps": 5, "total_tokens": 100, "target_tokens": 80, "span_durations_ms": [10, 20, 30], "total_duration_ms": 1000},
        {},
        {"target_tokens": 80, "p50_tokens": 100, "p50_latency_ms": 500},
    )
    assert result["step_efficiency"] == 50
    assert result["token_efficiency"] == 80
    assert result["latency_p50_ms"] == 20
    assert result["baseline_comparison"]["latency_ratio"] == 2
