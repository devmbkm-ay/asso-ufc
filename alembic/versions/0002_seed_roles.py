"""Seed default roles

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-03

Insert the 4 base roles so the app can function out of the box.
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


ROLES = [
    {"id": str(uuid.uuid4()), "name": "super_admin", "description": "Accès total — gestion de l'association"},
    {"id": str(uuid.uuid4()), "name": "treasurer",   "description": "Gestion des cotisations et de la trésorerie"},
    {"id": str(uuid.uuid4()), "name": "secretary",   "description": "Gestion des membres et des événements"},
    {"id": str(uuid.uuid4()), "name": "member",      "description": "Membre standard — accès en lecture"},
]


def upgrade() -> None:
    roles_table = sa.table(
        "roles",
        sa.column("id",          sa.String),
        sa.column("name",        sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(roles_table, ROLES)


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('super_admin','treasurer','secretary','member')")
