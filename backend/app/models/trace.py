import uuid
from sqlalchemy import Column, String, ForeignKey, Integer, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base


class TraceMetadata(Base):
    __tablename__ = "trace_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    trace_id = Column(String(64), nullable=False)
    root_span_id = Column(String(64), nullable=False)
    total_spans = Column(Integer, nullable=True)
    total_duration_ms = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    total_cost_usd = Column(Numeric(10, 6), nullable=True)
    error_spans = Column(Integer, default=0)
    storage_path = Column(String(500), nullable=False)
    spans_json_path = Column(String(500), nullable=True)
    snapshots_json_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
