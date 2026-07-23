"""Add password_resets table

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id",         sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("members.id"), nullable=False),
        sa.Column("token",      sa.String(64),  nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_password_resets_token", "password_resets", ["token"])
    op.create_index("ix_password_resets_member_id", "password_resets", ["member_id"])


def downgrade() -> None:
    op.drop_table("password_resets")
