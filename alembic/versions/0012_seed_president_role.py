"""Seed the president role

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-24
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ROLE_ID = str(uuid.uuid4())


def upgrade() -> None:
    roles_table = sa.table(
        "roles",
        sa.column("id",          sa.String),
        sa.column("name",        sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(roles_table, [
        {
            "id": ROLE_ID,
            "name": "president",
            "description": "Préside l'association — gestion des membres, événements, cotisations et invitations",
        },
    ])


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name = 'president'")
