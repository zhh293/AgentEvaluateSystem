from unittest.mock import AsyncMock

import pytest

from app.services.state_machine import EvaluationStateMachine
from app.services.websocket_service import WebSocketManager
from app.worker.tasks import aggregate_and_report, build_evaluation_dag


@pytest.mark.asyncio
async def test_state_machine_allows_only_declared_transitions():
    events = []
    machine = EvaluationStateMachine(on_transition=events.append)
    await machine.transition("validating")
    await machine.transition("validated")
    with pytest.raises(ValueError, match="非法"):
        await machine.transition("completed")
    assert len(events) == 2


@pytest.mark.asyncio
async def test_websocket_manager_connect_broadcast_disconnect():
    websocket = AsyncMock()
    manager = WebSocketManager()
    await manager.connect("s", websocket)
    await manager.broadcast("s", "progress", {"percent": 50})
    websocket.send_json.assert_awaited_once_with({"event": "progress", "data": {"percent": 50}})
    await manager.disconnect("s", websocket)
    assert "s" not in manager.active_connections


def test_aggregate_task_and_dag_are_serializable():
    report = aggregate_and_report.run([
        {"dimension": "result", "score": 100}, {"dimension": "trajectory", "score": 80},
        {"dimension": "efficiency", "score": 70}, {"dimension": "security", "score": 90},
    ], "short")
    assert report["status"] == "completed"
    assert report["overall_score"] == 88
    dag = build_evaluation_dag("submission", "evaluation", "short", ["case-1"])
    assert dag is not None


def test_evaluation_dag_requires_case_snapshots():
    with pytest.raises(ValueError, match="at least one"):
        build_evaluation_dag("submission", "evaluation", "short", [])
