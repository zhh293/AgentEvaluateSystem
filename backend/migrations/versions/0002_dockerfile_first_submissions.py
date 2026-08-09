"""Dockerfile-first submission build metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0002_dockerfile_first"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("submissions")}
    columns = (
        sa.Column("build_mode", sa.String(20), nullable=False, server_default="legacy"),
        sa.Column("dockerfile_path", sa.String(500), nullable=True),
        sa.Column("runtime_protocol", sa.String(20), nullable=False, server_default="stdio"),
        sa.Column("build_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("image_ref", sa.String(500), nullable=True),
        sa.Column("image_digest", sa.String(64), nullable=True),
        sa.Column("build_log_path", sa.String(500), nullable=True),
        sa.Column("sbom_path", sa.String(500), nullable=True),
        sa.Column("image_scan_path", sa.String(500), nullable=True),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("submissions", column)
    op.execute("UPDATE submissions SET status = 'reupload_required', build_status = 'reupload_required' WHERE image_ref IS NULL")


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("submissions")}
    for name in ("image_scan_path", "sbom_path", "build_log_path", "image_digest", "image_ref", "build_status", "runtime_protocol", "dockerfile_path", "build_mode"):
        if name in existing:
            op.drop_column("submissions", name)
