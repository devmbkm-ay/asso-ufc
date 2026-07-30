"""Add member_notifications table

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-31

In-app read/unread notification feed for members, distinct from the
existing `Notification` table which is an outbound email log. Seeded from
a small set of business events (designation validated/rejected, death
report confirmed) — see app/core/notifications.py.

Purely additive, no changes to existing tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_notifications",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",  postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=False),
        sa.Column("type",       sa.String(30), nullable=False),
        sa.Column("message",    sa.String(300), nullable=False),
        sa.Column("link",       sa.String(300), nullable=True),
        sa.Column("read",       sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("member_notifications")
