"""
Tests de fumée — vérifient que l'app démarre et répond sans base de données.
Ces tests n'ont pas besoin de PostgreSQL : toutes les routes DB retournent 500,
mais on s'assure que le routage, l'auth JWT et les schémas Pydantic fonctionnent.
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "a" * 64)

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_available():
    r = client.get("/docs")
    assert r.status_code == 200


def test_login_missing_body():
    r = client.post("/api/v1/auth/login", json={})
    assert r.status_code == 422


def test_login_invalid_credentials_format():
    r = client.post("/api/v1/auth/login", json={"email": "bad", "password": "x"})
    # 422 (validation email) ou 500 (DB indisponible) — pas de 200 sans DB
    assert r.status_code in (422, 500)


def test_protected_route_without_token():
    r = client.get("/api/v1/members")
    assert r.status_code in (401, 403)


def test_protected_route_invalid_token():
    r = client.get("/api/v1/members", headers={"Authorization": "Bearer token_invalide"})
    assert r.status_code == 401


def test_me_without_token():
    r = client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)
