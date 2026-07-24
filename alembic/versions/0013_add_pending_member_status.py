"""Add 'pending' value to the memberstatus enum

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-24

Adding a value to a Postgres enum type cannot be used in the same
transaction it was created in, so this is a standalone migration.
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE memberstatus ADD VALUE IF NOT EXISTS 'pending'")


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type.
    pass
