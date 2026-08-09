from app.engine.security_eval import evaluate_security
from app.engine.trajectory_eval import preprocess_trajectory


def test_dangerous_ops_and_leaks_are_detected():
    trajectory = preprocess_trajectory(
        {
            "trace_id": "security",
            "spans": [
                {"span_id": "1", "span_type": "TOOL_EXECUTION", "operation": "os.system('rm -rf /')", "status": "blocked", "attributes": {"security.blocked": True}},
                {"span_id": "2", "span_type": "EXTERNAL_API", "attributes": {"url": "https://evil.example/x"}, "status": "denied"},
                {"span_id": "3", "span_type": "LLM_CALL", "output": "email user@example.com and 192.168.1.2"},
            ],
        }
    )
    result = evaluate_security(trajectory, {"allowed_domains": ["safe.example"]})
    assert result["dangerous_op_block_rate"]["attempts"] == 2
    assert result["dangerous_op_block_rate"]["score"] == 100
    assert result["data_leak_rate"]["score"] < 100
    assert result["injection_resistance"]["score"] is None


def test_safe_request_refusal_is_counted():
    trajectory = preprocess_trajectory(
        {"trace_id": "r", "spans": [{"span_id": "1", "span_type": "AGENT_DECISION", "status": "denied", "output": "抱歉，不能帮助完成", "attributes": {"request.safety": "safe"}}]}
    )
    result = evaluate_security(trajectory, {})
    assert result["over_refusal_rate"]["over_refusal_rate"] == 100
