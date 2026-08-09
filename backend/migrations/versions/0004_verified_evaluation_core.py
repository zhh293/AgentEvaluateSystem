"""Verified intake, capability catalogs and case execution snapshots.

Revision ID: 0004_verified_core
Revises: 0003_compose_first
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_verified_core"
down_revision = "0003_compose_first"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(30), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_type", "owner_id", "artifact_type", "sha256", name="uq_artifact_content"),
    )
    op.create_index("ix_artifacts_owner_id", "artifacts", ["owner_id"])
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"])

    op.create_table(
        "verified_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "capability_catalogs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("spec_type", sa.String(20), nullable=False),
        sa.Column("spec_digest", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("capability_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capability_catalogs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_key", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("operation", postgresql.JSONB(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("constraints", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_pointer", sa.String(1000), nullable=False),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="declared"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("catalog_id", "capability_key", name="uq_capability_key"),
    )
    op.create_index("ix_capabilities_catalog_id", "capabilities", ["catalog_id"])

    op.create_table(
        "case_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capability_catalogs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("target_case_count", sa.Integer(), nullable=False),
        sa.Column("actual_case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("council_provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation_report", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_digest", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("submission_id", "version", name="uq_case_set_version"),
    )
    op.create_index("ix_case_sets_submission_id", "case_sets", ["submission_id"])
    op.create_table(
        "case_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_key", sa.String(150), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("suite", sa.String(30), nullable=False),
        sa.Column("horizon", sa.String(10), nullable=False),
        sa.Column("capability_ids", postgresql.JSONB(), nullable=False),
        sa.Column("setup", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("invocation", postgresql.JSONB(), nullable=False),
        sa.Column("constraints", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rubrics", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_set_id", "case_key", name="uq_case_definition_key"),
    )
    op.create_index("ix_case_definitions_case_set_id", "case_definitions", ["case_set_id"])

    op.add_column("evaluations", sa.Column("case_set_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_evaluations_case_set", "evaluations", "case_sets", ["case_set_id"], ["id"])
    op.create_table(
        "evaluation_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_sets.id"), nullable=False),
        sa.Column("case_key", sa.String(150), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("suite", sa.String(30), nullable=False),
        sa.Column("horizon", sa.String(10), nullable=False),
        sa.Column("capability_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("invocation", postgresql.JSONB(), nullable=False),
        sa.Column("rubrics", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("trace_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("dimension_scores", postgresql.JSONB(), nullable=True),
        sa.Column("unknown_weight", sa.String(30), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("evaluation_id", "case_key", name="uq_evaluation_case_key"),
    )
    op.create_index("ix_evaluation_cases_evaluation_id", "evaluation_cases", ["evaluation_id"])
    op.create_table(
        "execution_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("trace_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("evaluation_case_id", "attempt_number", name="uq_execution_attempt_number"),
    )
    op.create_index("ix_execution_attempts_evaluation_case_id", "execution_attempts", ["evaluation_case_id"])


def downgrade() -> None:
    op.drop_index("ix_execution_attempts_evaluation_case_id", table_name="execution_attempts")
    op.drop_table("execution_attempts")
    op.drop_index("ix_evaluation_cases_evaluation_id", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_constraint("fk_evaluations_case_set", "evaluations", type_="foreignkey")
    op.drop_column("evaluations", "case_set_id")
    op.drop_index("ix_case_definitions_case_set_id", table_name="case_definitions")
    op.drop_table("case_definitions")
    op.drop_index("ix_case_sets_submission_id", table_name="case_sets")
    op.drop_table("case_sets")
    op.drop_index("ix_capabilities_catalog_id", table_name="capabilities")
    op.drop_table("capabilities")
    op.drop_table("capability_catalogs")
    op.drop_table("verified_manifests")
    op.drop_index("ix_artifacts_artifact_type", table_name="artifacts")
    op.drop_index("ix_artifacts_owner_id", table_name="artifacts")
    op.drop_table("artifacts")
