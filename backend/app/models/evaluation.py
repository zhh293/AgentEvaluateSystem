import uuid
from sqlalchemy import Column, String, ForeignKey, Integer, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id"), nullable=True)
    status = Column(String(30), nullable=False, default="queued")
    agent_type = Column(String(50), nullable=False)
    horizon = Column(String(10), nullable=False)
    overall_score = Column(Numeric(5, 2), nullable=True)
    grade = Column(String(5), nullable=True)
    dimensions = Column(JSONB, nullable=True)
    skill_evaluation = Column(JSONB, nullable=True)
    attribution = Column(JSONB, nullable=True)
    improvement_suggestions = Column(JSONB, nullable=True)
    self_evaluation_loop = Column(JSONB, nullable=True)
    radar_chart_data = Column(JSONB, nullable=True)
    benchmark_comparison = Column(JSONB, nullable=True)
    report_full = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
