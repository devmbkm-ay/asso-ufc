"""Add goal_amount to collectes

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collectes", sa.Column("goal_amount", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("collectes", "goal_amount")
