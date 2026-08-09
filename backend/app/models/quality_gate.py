import uuid
from sqlalchemy import Column, String, ForeignKey, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base


class QualityGate(Base):
    __tablename__ = "quality_gates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    gate_type = Column(String(50), nullable=False)
    condition = Column(String(255), nullable=False)
    threshold = Column(String(50), nullable=False)
    actual_value = Column(String(50), nullable=False)
    passed = Column(Boolean, nullable=False)
    blocked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
