"""Add beneficiary_designations table

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-28

Lets a member designate up to 2 living people (family or otherwise) to
benefit from a solidarity collecte in case of death, for members who have
already lost their own close parents and can't benefit from the usual
mechanism (collecte triggered by the death of a member's relative).

Purely additive, no changes to existing tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beneficiary_designations",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",    postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=False),
        sa.Column("full_name",    sa.String(200), nullable=False),
        sa.Column("relation",     sa.String(100), nullable=False),
        sa.Column("contact",      sa.String(200), nullable=False),
        sa.Column("status",       sa.String(20), nullable=False, server_default="pending"),
        sa.Column("validated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_from",  sa.Date(), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("beneficiary_designations")
