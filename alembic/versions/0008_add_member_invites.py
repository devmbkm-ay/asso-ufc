"""Add member_invites table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_invites",
        sa.Column("id",         sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email",      sa.String(255), nullable=False),
        sa.Column("token",      sa.String(64),  nullable=False, unique=True),
        sa.Column("invited_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("members.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_member_invites_token", "member_invites", ["token"])
    op.create_index("ix_member_invites_email", "member_invites", ["email"])


def downgrade() -> None:
    op.drop_table("member_invites")
