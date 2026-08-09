from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SpanType(str, Enum):
    AGENT_EXECUTION = "AGENT_EXECUTION"
    AGENT_PLANNING = "AGENT_PLANNING"
    LLM_CALL = "LLM_CALL"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    AGENT_DECISION = "AGENT_DECISION"
    SKILL_EXECUTION = "SKILL_EXECUTION"
    RETRIEVAL = "RETRIEVAL"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    ENVIRONMENT_STATE_CHANGE = "ENVIRONMENT_STATE_CHANGE"
    EXTERNAL_API = "EXTERNAL_API"


class SpanData(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    span_type: SpanType
    operation: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    started_ns: int | None = None
    ended_ns: int | None = None
    duration_ms: float = 0.0
    status: str = "ok"
    input: dict[str, Any] | None = None
    output: Any = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tokens: int = 0
    error: str | None = None


class TrajectoryData(BaseModel):
    trace_id: str
    root_span_id: str = ""
    spans: list[SpanData] = Field(default_factory=list)
    environment_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    total_duration_ms: float = 0.0


class TraceData(TrajectoryData):
    total_spans: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    error_spans: int = 0
