import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    agent_name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    agent_type = Column(String(50), nullable=False)
    horizon = Column(String(10), nullable=False)
    subtype = Column(String(50), nullable=True)
    risk_level = Column(String(20), nullable=False, default="medium")
    config = Column(JSONB, nullable=False)
    source_package_path = Column(String(500), nullable=False)
    source_package_hash = Column(String(64), nullable=False)
    build_mode = Column(String(20), nullable=False, default="compose")
    deployment_type = Column(String(20), nullable=False, default="compose")
    compose_file = Column(String(500), nullable=True)
    entry_service = Column(String(100), nullable=False, default="agent")
    dockerfile_path = Column(String(500), nullable=True)
    runtime_protocol = Column(String(20), nullable=False, default="stdio")
    build_status = Column(String(30), nullable=False, default="pending")
    image_ref = Column(String(500), nullable=True)
    image_digest = Column(String(64), nullable=True)
    build_log_path = Column(String(500), nullable=True)
    sbom_path = Column(String(500), nullable=True)
    image_scan_path = Column(String(500), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    status_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
