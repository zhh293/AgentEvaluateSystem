import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(100), unique=True, nullable=False)
    agent_type = Column(String(50), nullable=False)
    horizon = Column(String(10), nullable=False)
    suite = Column(String(50), nullable=False)
    tier = Column(String(20), nullable=False, default="extended")
    prompt = Column(Text, nullable=False)
    context = Column(JSONB, nullable=True)
    expected_behavior = Column(JSONB, nullable=True)
    rubric = Column(JSONB, nullable=False)
    source = Column(String(50), default="manual")
    source_case_id = Column(String(100), nullable=True)
    status = Column(String(20), default="draft")
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
