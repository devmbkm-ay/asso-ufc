"""Add 'wero' value to the paymentmethod enum

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-25

Adding a value to a Postgres enum type cannot be used in the same
transaction it was created in, so this is a standalone migration —
mirrors 0011's approach for the rolename enum.
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'wero'")


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type.
    # Downgrading requires recreating the type manually if ever needed.
    pass
