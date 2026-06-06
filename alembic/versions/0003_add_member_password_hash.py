"""Add password_hash column to members

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-06

password_hash was missing from the initial schema migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ajout nullable d'abord car la table peut déjà contenir des lignes
    # (ex: si une autre migration a inséré des données de test).
    # Si la table est vide (cas normal au premier déploiement), on peut
    # directement passer en NOT NULL après.
    op.add_column("members", sa.Column("password_hash", sa.String(255), nullable=True))

    # Toute ligne existante sans mot de passe reçoit une valeur vide
    # pour pouvoir ensuite contraindre la colonne à NOT NULL.
    op.execute("UPDATE members SET password_hash = '' WHERE password_hash IS NULL")

    op.alter_column("members", "password_hash", nullable=False)


def downgrade() -> None:
    op.drop_column("members", "password_hash")
