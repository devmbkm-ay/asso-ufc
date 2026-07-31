"""
Infrastructure de test partagée : base Postgres jetable recréée à chaque run,
isolation par transaction/SAVEPOINT (un rollback complet après chaque test,
même si le code applicatif fait son propre db.commit()), et quelques membres
canoniques (un par rôle) commités une fois pour toute la session de tests.

Nécessite un Postgres accessible (docker-compose local ou service CI) —
voir README/docker-compose.yml pour les identifiants par défaut.
"""
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.environ.get("TEST_DB_PORT", "5432")
TEST_DB_USER = os.environ.get("TEST_DB_USER", "asso_user")
TEST_DB_PASSWORD = os.environ.get("TEST_DB_PASSWORD", "changeme")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "asso_db_test")

TEST_DATABASE_URL = (
    f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"
)
_MAINTENANCE_DATABASE_URL = (
    f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/postgres"
)

# app/core/config.py lit DATABASE_URL une seule fois, au premier import de
# app.core.database (donc de app.main) — doit être posé avant tout import de
# l'appli. conftest.py est toujours chargé avant les modules de test, donc
# c'est le bon endroit central pour ça (même contrainte que tests/test_smoke.py).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-" + "a" * 32)

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from models import Member, MemberRole, MemberStatus, Role, RoleName  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _recreate_test_database() -> None:
    maintenance_engine = create_engine(_MAINTENANCE_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    maintenance_engine.dispose()


def _migrate_test_database() -> None:
    alembic_cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def engine():
    _recreate_test_database()
    _migrate_test_database()
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def seed(engine):
    """
    Un membre par rôle, commité une fois pour toute la session — les tests
    individuels ne doivent jamais modifier ces lignes elles-mêmes (ils créent
    leurs propres données jetables dans leur transaction annulée après coup).
    Retourne un dict {clé: member_id}.
    """
    Session = sessionmaker(bind=engine)
    session = Session()

    # Les rôles sont déjà seedés par les migrations (0002_seed_roles.py) —
    # on les relit plutôt que de les recréer.
    roles = {row.name: row for row in session.query(Role).all()}

    def make_member(email: str, first_name: str, last_name: str, role_names: list[RoleName]) -> Member:
        member = Member(
            id=uuid.uuid4(),
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=hash_password("Test1234!"),
            status=MemberStatus.active,
        )
        session.add(member)
        session.flush()
        for role_name in role_names:
            session.add(MemberRole(id=uuid.uuid4(), member_id=member.id, role_id=roles[role_name].id))
        return member

    members = {
        "super_admin": make_member("super_admin@example.com", "Super", "Admin", [RoleName.super_admin]),
        "president": make_member("president@example.com", "Pres", "Ident", [RoleName.president]),
        "treasurer": make_member("treasurer@example.com", "Treas", "Urer", [RoleName.treasurer]),
        "secretary": make_member("secretary@example.com", "Secre", "Tary", [RoleName.secretary]),
        "member1": make_member("member1@example.com", "Awa", "Membre1", [RoleName.member]),
        "member2": make_member("member2@example.com", "Brice", "Membre2", [RoleName.member]),
    }
    session.commit()
    ids = {key: member.id for key, member in members.items()}
    session.close()
    return ids


@pytest.fixture()
def db(engine, seed):
    """
    Session bornée à une connexion + transaction externe, avec les commits
    applicatifs traités comme de simples SAVEPOINT (join_transaction_mode=
    "create_savepoint", SQLAlchemy 2.0) — tout est annulé en fin de test,
    quel que soit le nombre de db.commit() faits par les routes appelées.
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = TestSession()

    app.dependency_overrides[get_db] = lambda: session

    yield session

    app.dependency_overrides.pop(get_db, None)
    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def auth_headers(member_id: uuid.UUID, roles: list[str] | None = None) -> dict[str, str]:
    """Jeton valide pour member_id — les rôles réels utilisés pour les permissions
    sont toujours relus en base par les routes, le contenu de `roles` ici ne sert
    qu'au payload JWT (cf. app/core/deps.py, aucune route ne s'y fie directement)."""
    token = create_access_token(member_id, roles or [])
    return {"Authorization": f"Bearer {token}"}
