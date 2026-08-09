import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "artifact_type", "sha256", name="uq_artifact_content"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type = Column(String(30), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    artifact_type = Column(String(50), nullable=False, index=True)
    storage_path = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False)
    media_type = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    schema_version = Column(String(20), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class VerifiedManifest(Base):
    __tablename__ = "verified_manifests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True)
    schema_version = Column(String(20), nullable=False, default="1")
    manifest = Column(JSONB, nullable=False)
    input_digest = Column(String(64), nullable=False)
    manifest_digest = Column(String(64), nullable=False)
    generator_version = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
