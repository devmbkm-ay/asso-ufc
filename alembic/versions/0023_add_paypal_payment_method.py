"""Add 'paypal' value to the paymentmethod enum

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-06

Adding a value to a Postgres enum type cannot be used in the same
transaction it was created in, so this is a standalone migration —
mirrors 0015's approach for the same enum.
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'paypal'")


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type.
    # Downgrading requires recreating the type manually if ever needed.
    pass
