import json

import pytest
from pywebpush import WebPushException

import app.core.notifications as notifications_module
from tests.conftest import auth_headers
from models import PushSubscription

SUB_A = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/aaa",
    "keys": {"p256dh": "p256dh-a", "auth": "auth-a"},
}


def test_subscribe_then_unsubscribe(client, seed, db):
    r = client.post("/api/v1/push/subscriptions", json=SUB_A, headers=auth_headers(seed["member1"]))
    assert r.status_code == 204

    row = db.query(PushSubscription).filter(PushSubscription.endpoint == SUB_A["endpoint"]).first()
    assert row is not None
    assert row.member_id == seed["member1"]

    r = client.request("DELETE", "/api/v1/push/subscriptions",
                        json={"endpoint": SUB_A["endpoint"]}, headers=auth_headers(seed["member1"]))
    assert r.status_code == 204

    row = db.query(PushSubscription).filter(PushSubscription.endpoint == SUB_A["endpoint"]).first()
    assert row is None


def test_resubscribing_same_endpoint_reassigns_member(client, seed, db):
    client.post("/api/v1/push/subscriptions", json=SUB_A, headers=auth_headers(seed["member1"]))
    client.post("/api/v1/push/subscriptions", json=SUB_A, headers=auth_headers(seed["member2"]))

    rows = db.query(PushSubscription).filter(PushSubscription.endpoint == SUB_A["endpoint"]).all()
    assert len(rows) == 1
    assert rows[0].member_id == seed["member2"]


def test_vapid_public_key_accessible_to_any_authenticated_member(client, seed):
    r = client.get("/api/v1/push/vapid-public-key", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200
    assert "public_key" in r.json()


def test_notify_member_sends_push_to_subscription(client, seed, db, monkeypatch):
    client.post("/api/v1/push/subscriptions", json=SUB_A, headers=auth_headers(seed["member1"]))

    calls = []
    monkeypatch.setattr(notifications_module, "webpush", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(notifications_module.settings, "VAPID_PRIVATE_KEY", "test-private-key")

    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))

    assert len(calls) == 1
    assert calls[0]["subscription_info"]["endpoint"] == SUB_A["endpoint"]
    body = json.loads(calls[0]["data"])
    assert "X" in body["body"]


def test_notify_member_removes_subscription_on_410(client, seed, db, monkeypatch):
    client.post("/api/v1/push/subscriptions", json=SUB_A, headers=auth_headers(seed["member1"]))

    class FakeResponse:
        status_code = 410

    def raise_gone(**kwargs):
        raise WebPushException("gone", response=FakeResponse())

    monkeypatch.setattr(notifications_module, "webpush", raise_gone)
    monkeypatch.setattr(notifications_module.settings, "VAPID_PRIVATE_KEY", "test-private-key")

    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    r = client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200  # l'action métier réussit malgré l'échec d'envoi push

    row = db.query(PushSubscription).filter(PushSubscription.endpoint == SUB_A["endpoint"]).first()
    assert row is None
