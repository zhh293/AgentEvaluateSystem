import uuid
from sqlalchemy import Column, String, Integer, DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Numeric(12, 3), nullable=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
