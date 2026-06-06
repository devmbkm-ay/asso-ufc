"""Add is_archived, archived_at, category to collectes

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collectes", sa.Column("category",    sa.String(50),              nullable=True))
    op.add_column("collectes", sa.Column("is_archived", sa.Boolean,                 nullable=False, server_default="false"))
    op.add_column("collectes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("collectes", "archived_at")
    op.drop_column("collectes", "is_archived")
    op.drop_column("collectes", "category")
