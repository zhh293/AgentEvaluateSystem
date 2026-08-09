from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Callable


class EvaluationStateMachine:
    TRANSITIONS = {
        "pending": {"validating", "failed"},
        "validating": {"validated", "failed"},
        "validated": {"sandbox_creating", "failed"},
        "sandbox_creating": {"sandbox_ready", "failed"},
        "sandbox_ready": {"running", "failed"},
        "running": {"aggregating", "failed"},
        "aggregating": {"completed", "failed"},
        "completed": set(),
        "failed": set(),
    }

    def __init__(self, initial_state: str = "pending", on_transition: Callable[[dict], Any] | None = None):
        if initial_state not in self.TRANSITIONS:
            raise ValueError(f"unknown state: {initial_state}")
        self.current_state = initial_state
        self.history = []
        self.on_transition = on_transition

    async def transition(self, new_state: str, metadata: dict | None = None) -> dict:
        if new_state not in self.TRANSITIONS[self.current_state]:
            raise ValueError(f"非法状态转换: {self.current_state} → {new_state}")
        event = {"from": self.current_state, "to": new_state, "metadata": metadata or {}, "timestamp": datetime.now(timezone.utc).isoformat()}
        self.current_state = new_state
        self.history.append(event)
        if self.on_transition:
            result = self.on_transition(event)
            if inspect.isawaitable(result):
                await result
        return event
