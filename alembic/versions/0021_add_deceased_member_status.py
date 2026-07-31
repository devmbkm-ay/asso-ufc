"""Add 'deceased' value to memberstatus enum

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-31

Lets a member's status reflect that they have died — set automatically
when a sens-A death report (about the member themselves, not a designated
person) is confirmed (see app/api/v1/routes/death_reports.py). Standalone
migration: Postgres requires adding an enum value in its own transaction,
can't be used in the same transaction it was added in — same pattern as
0015_add_wero_payment_method.py.
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE memberstatus ADD VALUE IF NOT EXISTS 'deceased'")


def downgrade() -> None:
    # Postgres ne permet pas de retirer une valeur d'un type enum existant.
    pass
