import uuid
from sqlalchemy import Column, String, ForeignKey, Boolean, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class SkillEvaluation(Base):
    __tablename__ = "skill_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    skill_name = Column(String(255), nullable=False)
    single_score = Column(Numeric(5, 2), nullable=True)
    integration_score = Column(Numeric(5, 2), nullable=True)
    single_pass = Column(Boolean, nullable=True)
    integration_pass = Column(Boolean, nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
