"""Add 'president' value to the rolename enum

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-24

Adding a value to a Postgres enum type cannot be used in the same
transaction it was created in, so this is a standalone migration —
the seed insert happens in 0012.
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'president'")


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type.
    # Downgrading requires recreating the type manually if ever needed.
    pass
