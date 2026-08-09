from datetime import datetime
from pydantic import BaseModel


class SpanData(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    operation: str
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int | None = None
    status: str = "ok"
    input: dict | None = None
    output: dict | None = None
    tokens: int = 0
    error: str | None = None


class TraceData(BaseModel):
    trace_id: str
    root_span_id: str
    total_spans: int
    total_duration_ms: int
    total_tokens: int
    total_cost_usd: float = 0.0
    error_spans: int = 0
    spans: list[SpanData] = []
