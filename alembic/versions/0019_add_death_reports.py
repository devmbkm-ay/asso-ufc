"""Add death_reports table

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-29

Lets a member report the death of another member (sens A — the collecte
should then support that member's own validated designated beneficiaries)
or the death of a person they had themselves designated (sens B — the
collecte should then support the designating member, mirroring the usual
mechanism where a relative's death triggers a collecte for the member).
An admin/president reviews before a collecte is manually created via the
existing flow.

Purely additive, no changes to existing tables besides a new nullable
tracing column on collectes.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "death_reports",
        sa.Column("id",             postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",      postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("designation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("beneficiary_designations.id"), nullable=True),
        sa.Column("reported_by",    postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=False),
        sa.Column("note",           sa.Text(), nullable=True),
        sa.Column("status",         sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by",    postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("reviewed_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "collectes",
        sa.Column("beneficiary_designation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("beneficiary_designations.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collectes", "beneficiary_designation_id")
    op.drop_table("death_reports")