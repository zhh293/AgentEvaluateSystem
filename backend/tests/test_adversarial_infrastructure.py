import pytest

from app.engine.adversarial import PAIRGenerator, TAPGenerator, load_static_cases, run_static_adversarial_eval
from app.infrastructure.quality_gate import QualityGateEngine
from app.infrastructure.regression import RegressionEngine
from app.infrastructure.replay import TraceReplayEngine


def test_static_library_has_one_hundred_cases_across_five_categories():
    cases = load_static_cases()
    assert len(cases) == 100
    assert len({item["id"] for item in cases}) == 100
    assert len({item["category"] for item in cases}) == 5
    assert all(item["expected_defense"] and item["risk_level"] == "high" for item in cases)


@pytest.mark.asyncio
async def test_static_eval_computes_defense_score():
    result = await run_static_adversarial_eval(load_static_cases()[:2], lambda case: {"defended": case["id"] == "ADV-001", "attack_succeeded": case["id"] == "ADV-002"})
    assert result["score"] == 50


@pytest.mark.asyncio
async def test_pair_stops_after_success_and_tap_prunes():
    attempts = 0
    async def attack(prompt):
        nonlocal attempts
        attempts += 1
        return {"attack_succeeded": attempts >= 2, "value": attempts}
    pair = PAIRGenerator(lambda prompt, feedback: prompt + "!", attack)
    assert len(await pair.generate_variants("seed", 10)) == 2
    tap = TAPGenerator(lambda prompt, width: [prompt + str(i) for i in range(width)], lambda prompt: {"attack_succeeded": prompt.endswith("1")}, lambda result: 1 if result["attack_succeeded"] else 0)
    paths = await tap.search_attack_paths("seed", max_depth=2, beam_width=2)
    assert paths[0]["score"] == 1


def test_replay_navigation_snapshot_and_diff():
    replay = TraceReplayEngine({"spans": [{"span_id": "b", "started_ns": 2, "span_type": "LLM_CALL"}, {"span_id": "a", "started_ns": 1, "span_type": "TOOL_EXECUTION"}], "environment_snapshots": [{"timestamp_ms": 1, "state": {"a": 1}}, {"timestamp_ms": 2, "state": {"a": 2, "b": 3}}]})
    assert replay.step_forward()["span_id"] == "a"
    assert replay.jump_to("b")["span_id"] == "b"
    assert replay.filter_by_type("TOOL_EXECUTION")[0]["span_id"] == "a"
    assert replay.compare_snapshots(1, 2)["changed"]["a"]["after"] == 2


def test_regression_and_quality_gates_block_failures():
    regression = RegressionEngine()
    assert regression.should_trigger_regression({"llm_model": "b"}, {"llm_model": "a"})
    assert not regression.compare_with_baseline({"score": 90}, {"score": 100})["passed"]
    gates = QualityGateEngine()
    assert gates.check_gate("skill_launch", {"pass_rate": 90})["passed"]
    assert not gates.check_gate("ops_monitor", {"success_rate": 90, "satisfaction": 3.9})["passed"]
