import uuid
from datetime import date

from tests.conftest import auth_headers
from models import Payment, PaymentMethod, PaymentStatus


def _make_one_time_plan(client, seed):
    r = client.post("/api/v1/cotisation-plans", json={
        "label": "Cotisation de test",
        "amount": 15,
        "frequency": "one_time",
        "valid_from": date.today().isoformat(),
    }, headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 201
    return r.json()["id"]


def _my_pending_payment(client, seed, member_key):
    r = client.get("/api/v1/payments", params={
        "member_id": str(seed[member_key]), "status": "pending", "size": 50,
    }, headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "attendu au moins un paiement pending après init du plan"
    return items[0]["id"]


def test_declare_then_validate_payment(client, seed):
    _make_one_time_plan(client, seed)
    payment_id = _my_pending_payment(client, seed, "member1")

    r = client.post(f"/api/v1/payments/{payment_id}/confirm", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200
    assert r.json()["status"] == "declared"

    r = client.post(f"/api/v1/payments/{payment_id}/validate", headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    assert any(n["type"] == "payment_validated" for n in r.json())


def test_reject_declared_payment_reverts_to_pending(client, seed):
    _make_one_time_plan(client, seed)
    payment_id = _my_pending_payment(client, seed, "member1")
    client.post(f"/api/v1/payments/{payment_id}/confirm", headers=auth_headers(seed["member1"]))

    r = client.post(f"/api/v1/payments/{payment_id}/reject", headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    assert any(n["type"] == "payment_rejected" for n in r.json())


def test_validating_payment_reactivates_inactive_member(client, seed):
    r = client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "inactive"},
                      headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200

    _make_one_time_plan(client, seed)
    payment_id = _my_pending_payment(client, seed, "member1")
    client.post(f"/api/v1/payments/{payment_id}/confirm", headers=auth_headers(seed["member1"]))

    r = client.post(f"/api/v1/payments/{payment_id}/validate", headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 200

    r = client.get("/api/v1/members", params={"status": "active"}, headers=auth_headers(seed["super_admin"]))
    assert any(m["id"] == str(seed["member1"]) for m in r.json()["items"])


def test_deceased_member_never_auto_reactivated(client, seed, db):
    """Le code de validate_declared_payment ne teste que status == inactive
    -- un membre deceased ne doit jamais repasser active par ce chemin."""
    r = client.patch(f"/api/v1/members/{seed['member2']}/status", json={"status": "deceased"},
                      headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200

    plan_id = _make_one_time_plan(client, seed)

    # Un membre déceased est exclu de l'auto-init des paiements (filtre
    # active/inactive) -- on insère donc directement la ligne "declared"
    # pour pouvoir exercer validate_declared_payment sur lui.
    payment = Payment(
        id=uuid.uuid4(),
        member_id=seed["member2"],
        cotisation_plan_id=uuid.UUID(plan_id),
        amount=15,
        payment_date=date.today(),
        period_month=None,
        period_year=date.today().year,
        method=PaymentMethod.cash,
        status=PaymentStatus.declared,
    )
    db.add(payment)
    db.commit()

    r = client.post(f"/api/v1/payments/{payment.id}/validate", headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 200

    r = client.get("/api/v1/members", params={"status": "deceased"}, headers=auth_headers(seed["super_admin"]))
    assert any(m["id"] == str(seed["member2"]) for m in r.json()["items"])


def test_payment_flags_deceased_member(client, seed, db):
    r = client.patch(f"/api/v1/members/{seed['member2']}/status", json={"status": "deceased"},
                      headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200

    plan_id = _make_one_time_plan(client, seed)
    payment = Payment(
        id=uuid.uuid4(),
        member_id=seed["member2"],
        cotisation_plan_id=uuid.UUID(plan_id),
        amount=15,
        payment_date=date.today(),
        period_month=None,
        period_year=date.today().year,
        method=PaymentMethod.cash,
        status=PaymentStatus.declared,
    )
    db.add(payment)
    db.commit()

    r = client.get("/api/v1/payments", params={"member_id": str(seed["member2"]), "size": 50},
                    headers=auth_headers(seed["treasurer"]))
    found = next(p for p in r.json()["items"] if p["id"] == str(payment.id))
    assert found["member_deceased"] is True
