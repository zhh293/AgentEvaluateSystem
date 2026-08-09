"""initial schema including evaluation, security and audit entities

Revision ID: 0001_initial
Revises:
"""

from alembic import op

from app.models import Base  # imports and registers every model


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
