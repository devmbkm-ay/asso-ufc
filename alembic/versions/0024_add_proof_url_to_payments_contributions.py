"""Add proof_url to payments and contributions

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-06

Optional screenshot/receipt attached by the member when declaring a
payment, reviewed by the treasurer alongside the existing reference
code — not required to declare, purely supplementary evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("proof_url", sa.String(500), nullable=True))
    op.add_column("contributions", sa.Column("proof_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("contributions", "proof_url")
    op.drop_column("payments", "proof_url")
