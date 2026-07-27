"""Add login_events table

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-27

One row per successful login. Purely additive, no changes to existing
tables. Feeds the admin dashboard's usage-frequency stats (active members
over 7/30 days, never-logged-in) — distinct from audit_logs, which
journalizes data mutations, not access.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",  postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("login_events")
