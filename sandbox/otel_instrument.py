"""Minimal GenAI-oriented trace recorder with optional OpenTelemetry export."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator


SPAN_TYPES = (
    "AGENT_EXECUTION",
    "AGENT_PLANNING",
    "LLM_CALL",
    "TOOL_EXECUTION",
    "AGENT_DECISION",
    "SKILL_EXECUTION",
    "RETRIEVAL",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "ENVIRONMENT_STATE_CHANGE",
    "EXTERNAL_API",
)

_SECRET_MARKERS = ("key", "secret", "token", "authorization", "password")


class TraceRecorder:
    def __init__(self) -> None:
        self.trace_id = uuid.uuid4().hex
        self.spans: list[dict[str, Any]] = []
        self._stack: list[str] = []

    @contextmanager
    def span(self, span_type: str, attributes: dict[str, Any] | None = None) -> Iterator[str]:
        if span_type not in SPAN_TYPES:
            raise ValueError(f"unsupported span type: {span_type}")
        span_id = uuid.uuid4().hex[:16]
        started_ns = time.time_ns()
        record = {
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": self._stack[-1] if self._stack else None,
            "span_type": span_type,
            "started_ns": started_ns,
            "attributes": self._sanitize(attributes or {}),
            "status": "ok",
        }
        self._stack.append(span_id)
        try:
            yield span_id
        except Exception as exc:
            record["status"] = "error"
            record["error.type"] = type(exc).__name__
            raise
        finally:
            self._stack.pop()
            record["ended_ns"] = time.time_ns()
            record["duration_ms"] = (record["ended_ns"] - started_ns) / 1_000_000
            self.spans.append(record)

    @staticmethod
    def _sanitize(attributes: dict[str, Any]) -> dict[str, Any]:
        return {
            key: "[REDACTED]" if any(marker in key.lower() for marker in _SECRET_MARKERS) else value
            for key, value in attributes.items()
        }

    def to_json(self) -> str:
        return json.dumps({"trace_id": self.trace_id, "spans": self.spans}, ensure_ascii=False)
