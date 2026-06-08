"""add declared to paymentstatus enum

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-08
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL allows adding enum values; IF NOT EXISTS avoids error on re-run
    op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'declared'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — left intentionally empty
    pass
