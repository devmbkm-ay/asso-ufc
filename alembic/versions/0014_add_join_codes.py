"""Add join_codes table

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "join_codes",
        sa.Column("id",         sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code",       sa.String(16), nullable=False, unique=True),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("members.id"), nullable=False),
        sa.Column("is_active",  sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_join_codes_code", "join_codes", ["code"])
    op.create_index("ix_join_codes_is_active", "join_codes", ["is_active"])


def downgrade() -> None:
    op.drop_table("join_codes")
