from app.engine.result_eval import (
    evaluate_accuracy,
    evaluate_long_horizon,
    evaluate_safety,
    evaluate_short_horizon,
)


def test_exact_answer_scores_full_accuracy():
    assert evaluate_accuracy("北京", "北京")["score"] == 100


def test_missing_ground_truth_is_unknown_not_fake_score():
    metric = evaluate_accuracy("北京", None)
    assert metric["score"] is None
    assert metric["judge_type"] == "pending_llm"


def test_safety_detects_pii_and_api_keys():
    result = evaluate_safety("联系 13812345678，密钥 sk-1234567890abcdef")
    assert result["score"] < 100
    assert result["details"]["pii_hits"]["phone"] == 1
    assert result["details"]["pii_hits"]["api_key"] == 1


def test_short_horizon_has_all_six_metrics():
    result = evaluate_short_horizon("答案", "答案", "问题")
    assert set(result) == {"accuracy", "relevance", "fluency", "helpfulness", "safety", "coherence"}
    assert result["relevance"]["score"] is None


def test_long_horizon_checks_criteria_and_nested_outcome():
    result = evaluate_long_horizon(
        {"file": {"created": True, "name": "report.pdf"}, "rows": 10},
        {
            "success_criteria": [
                {"path": "file.created", "equals": True},
                {"path": "rows", "min": 5},
            ],
            "expected_outcome": {"file": {"name": "report.pdf"}},
        },
        {},
    )
    assert result["task_success_rate"]["score"] == 100
    assert result["result_correctness"]["score"] == 100
