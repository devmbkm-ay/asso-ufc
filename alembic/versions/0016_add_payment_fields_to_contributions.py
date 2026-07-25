"""Add method/status/reference/recorded_by to contributions

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-25

Extends Contribution with the same declare/confirm traceability fields
Payment already has (method, status, reference, recorded_by), so collecte
contributions can go through the same pending -> declared -> confirmed
flow as cotisation payments. Existing rows are backfilled as already
"final" money received (status=confirmed, method=other), matching how
Payment.status defaults to confirmed for treasurer-recorded entries.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contributions",
        sa.Column(
            "method",
            sa.Enum(name="paymentmethod", create_type=False),
            nullable=False,
            server_default="other",
        ),
    )
    op.add_column(
        "contributions",
        sa.Column(
            "status",
            sa.Enum(name="paymentstatus", create_type=False),
            nullable=False,
            server_default="confirmed",
        ),
    )
    op.add_column("contributions", sa.Column("reference", sa.String(200), nullable=True))
    op.add_column(
        "contributions",
        sa.Column(
            "recorded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_contributions_status", "contributions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_contributions_status", table_name="contributions")
    op.drop_column("contributions", "recorded_by")
    op.drop_column("contributions", "reference")
    op.drop_column("contributions", "status")
    op.drop_column("contributions", "method")
