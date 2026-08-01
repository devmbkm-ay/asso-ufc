"""Add push_subscriptions table

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-01

Web Push subscriptions (one member can have several — one per browser/
device). Consumed by notify_member() in app/core/notifications.py, which
sends a real push alongside the existing in-app MemberNotification row.

Purely additive, no changes to existing tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",  postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=False),
        sa.Column("endpoint",   sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh",     sa.String(255), nullable=False),
        sa.Column("auth",       sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
