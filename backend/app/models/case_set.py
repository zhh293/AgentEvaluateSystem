import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class CaseSet(Base):
    __tablename__ = "case_sets"
    __table_args__ = (UniqueConstraint("submission_id", "version", name="uq_case_set_version"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    capability_catalog_id = Column(UUID(as_uuid=True), ForeignKey("capability_catalogs.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default="pending")
    target_case_count = Column(Integer, nullable=False)
    actual_case_count = Column(Integer, nullable=False, default=0)
    coverage = Column(JSONB, nullable=False, default=dict)
    council_provenance = Column(JSONB, nullable=False, default=dict)
    validation_report = Column(JSONB, nullable=False, default=dict)
    content_digest = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CaseDefinition(Base):
    __tablename__ = "case_definitions"
    __table_args__ = (UniqueConstraint("case_set_id", "case_key", name="uq_case_definition_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_set_id = Column(UUID(as_uuid=True), ForeignKey("case_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    case_key = Column(String(150), nullable=False)
    title = Column(String(500), nullable=False)
    suite = Column(String(30), nullable=False)
    horizon = Column(String(10), nullable=False)
    capability_ids = Column(JSONB, nullable=False)
    setup = Column(JSONB, nullable=False, default=list)
    invocation = Column(JSONB, nullable=False)
    constraints = Column(JSONB, nullable=False, default=dict)
    rubrics = Column(JSONB, nullable=False)
    provenance = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (UniqueConstraint("evaluation_id", "case_key", name="uq_evaluation_case_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True)
    case_set_id = Column(UUID(as_uuid=True), ForeignKey("case_sets.id"), nullable=False)
    case_key = Column(String(150), nullable=False)
    title = Column(String(500), nullable=False)
    suite = Column(String(30), nullable=False)
    horizon = Column(String(10), nullable=False)
    capability_ids = Column(JSONB, nullable=False, default=list)
    invocation = Column(JSONB, nullable=False)
    rubrics = Column(JSONB, nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    result = Column(JSONB, nullable=True)
    trace_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True)
    dimension_scores = Column(JSONB, nullable=True)
    unknown_weight = Column(String(30), nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (UniqueConstraint("evaluation_case_id", "attempt_number", name="uq_execution_attempt_number"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_case_id = Column(UUID(as_uuid=True), ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="running")
    result = Column(JSONB, nullable=True)
    trace_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
