import uuid
from sqlalchemy import Column, String, ForeignKey, Integer, Boolean, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class SelfEvalLoopRun(Base):
    __tablename__ = "self_eval_loop_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    attempt_number = Column(Integer, nullable=False)
    score_before = Column(Numeric(5, 2), nullable=True)
    score_after = Column(Numeric(5, 2), nullable=True)
    attributions = Column(JSONB, nullable=True)
    corrections = Column(JSONB, nullable=True)
    all_rubrics_passed = Column(Boolean, nullable=True)
    degraded = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
