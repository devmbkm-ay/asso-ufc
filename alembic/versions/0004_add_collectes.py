"""Add collectes and contributions tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collectes",
        sa.Column("id",               sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title",            sa.String(300), nullable=False),
        sa.Column("beneficiary_name", sa.String(200), nullable=False),
        sa.Column("photo_url",        sa.String(500), nullable=True),
        sa.Column("description",      sa.Text,        nullable=True),
        sa.Column("min_amount",       sa.Numeric(10, 2), nullable=False, server_default="20.00"),
        sa.Column("start_date",       sa.Date,        nullable=False),
        sa.Column("end_date",         sa.Date,        nullable=False),
        sa.Column("is_closed",        sa.Boolean,     nullable=False, server_default="false"),
        sa.Column("created_by",       sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("members.id"), nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "contributions",
        sa.Column("id",             sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("collecte_id",    sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("collectes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id",      sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("members.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("amount",         sa.Numeric(10, 2), nullable=False),
        sa.Column("contributed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_contributions_collecte_id", "contributions", ["collecte_id"])
    op.create_index("ix_contributions_member_id",   "contributions", ["member_id"])


def downgrade() -> None:
    op.drop_table("contributions")
    op.drop_table("collectes")
