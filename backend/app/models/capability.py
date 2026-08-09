import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class CapabilityCatalog(Base):
    __tablename__ = "capability_catalogs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default="pending")
    spec_type = Column(String(20), nullable=False)
    spec_digest = Column(String(64), nullable=False)
    parser_version = Column(String(50), nullable=False)
    capability_count = Column(Integer, nullable=False, default=0)
    warnings = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Capability(Base):
    __tablename__ = "capabilities"
    __table_args__ = (UniqueConstraint("catalog_id", "capability_key", name="uq_capability_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    catalog_id = Column(UUID(as_uuid=True), ForeignKey("capability_catalogs.id", ondelete="CASCADE"), nullable=False, index=True)
    capability_key = Column(String(300), nullable=False)
    kind = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    operation = Column(JSONB, nullable=False)
    input_schema = Column(JSONB, nullable=False, default=dict)
    output_schema = Column(JSONB, nullable=False, default=dict)
    constraints = Column(JSONB, nullable=False, default=list)
    source_pointer = Column(String(1000), nullable=False)
    verification_status = Column(String(20), nullable=False, default="declared")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
