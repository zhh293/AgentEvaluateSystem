import uuid
from sqlalchemy import Column, String, ForeignKey, Integer, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    test_case_id = Column(String(100), nullable=False)
    test_suite = Column(String(50), nullable=False)
    dimension = Column(String(50), nullable=False)
    metric_name = Column(String(100), nullable=False)
    rubric_id = Column(String(50), nullable=True)
    score = Column(Numeric(5, 2), nullable=True)
    max_score = Column(Numeric(5, 2), nullable=True)
    judge_type = Column(String(30), nullable=True)
    judge_a_score = Column(Numeric(5, 2), nullable=True)
    judge_b_score = Column(Numeric(5, 2), nullable=True)
    judge_c_score = Column(Numeric(5, 2), nullable=True)
    agreement_level = Column(Numeric(3, 2), nullable=True)
    details = Column(JSONB, nullable=True)
    trace_storage_path = Column(String(500), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
