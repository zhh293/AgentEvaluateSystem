"""Compose-first deployment metadata.

Revision ID: 0003_compose_first
Revises: 0002_dockerfile_first
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_compose_first"
down_revision = "0002_dockerfile_first"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("submissions")}
    columns = (
        sa.Column("deployment_type", sa.String(20), nullable=False, server_default="compose"),
        sa.Column("compose_file", sa.String(500), nullable=True),
        sa.Column("entry_service", sa.String(100), nullable=False, server_default="agent"),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("submissions", column)
    op.execute("UPDATE submissions SET deployment_type = CASE WHEN build_mode = 'compose' THEN 'compose' ELSE 'image' END")
    op.alter_column("submissions", "build_mode", server_default="compose")


def downgrade() -> None:
    op.alter_column("submissions", "build_mode", server_default="legacy")
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("submissions")}
    for name in ("entry_service", "compose_file", "deployment_type"):
        if name in existing:
            op.drop_column("submissions", name)
