from datetime import date

from tests.conftest import auth_headers


def _make_collecte(client, seed, min_amount=10):
    r = client.post("/api/v1/collectes", json={
        "title": "Collecte de test",
        "beneficiary_name": "Beneficiaire Test",
        "start_date": date.today().isoformat(),
        "category": "autre",
        "min_amount": min_amount,
    }, headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 201
    return r.json()["id"]


def test_contribute_then_declare_then_validate(client, seed):
    collecte_id = _make_collecte(client, seed)

    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions",
                     json={"amount": 20, "method": "cash"}, headers=auth_headers(seed["member1"]))
    assert r.status_code == 201
    contribution_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/confirm",
                     headers=auth_headers(seed["member1"]))
    assert r.status_code == 200
    assert r.json()["status"] == "declared"

    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/validate",
                     headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    notif = next((n for n in r.json() if n["type"] == "contribution_validated"), None)
    assert notif is not None
    assert "Collecte de test" in notif["message"]


def test_reject_declared_contribution_reverts_to_pending(client, seed):
    collecte_id = _make_collecte(client, seed)
    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions",
                     json={"amount": 20, "method": "cash"}, headers=auth_headers(seed["member1"]))
    contribution_id = r.json()["id"]
    client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/confirm",
                headers=auth_headers(seed["member1"]))

    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/reject",
                     headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    assert any(n["type"] == "contribution_rejected" for n in r.json())


def test_self_validation_is_allowed(client, seed):
    """Pas de garde-fou contre l'auto-validation — cf. décision prise en
    diagnostiquant le problème "je ne peux pas valider mon propre paiement"."""
    collecte_id = _make_collecte(client, seed)
    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions",
                     json={"amount": 20, "method": "cash"}, headers=auth_headers(seed["super_admin"]))
    contribution_id = r.json()["id"]
    client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/confirm",
                headers=auth_headers(seed["super_admin"]))

    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/validate",
                     headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


def test_non_validator_cannot_validate(client, seed):
    collecte_id = _make_collecte(client, seed)
    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions",
                     json={"amount": 20, "method": "cash"}, headers=auth_headers(seed["member1"]))
    contribution_id = r.json()["id"]
    client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/confirm",
                headers=auth_headers(seed["member1"]))

    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions/{contribution_id}/validate",
                     headers=auth_headers(seed["member2"]))
    assert r.status_code == 403


def test_minimum_amount_enforced(client, seed):
    collecte_id = _make_collecte(client, seed, min_amount=50)
    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions",
                     json={"amount": 10, "method": "cash"}, headers=auth_headers(seed["member1"]))
    assert r.status_code == 400


def test_contribution_flags_deceased_member(client, seed):
    collecte_id = _make_collecte(client, seed)
    r = client.post(f"/api/v1/collectes/{collecte_id}/contributions",
                     json={"amount": 20, "method": "cash"}, headers=auth_headers(seed["member1"]))
    contribution_id = r.json()["id"]
    assert r.json()["member_deceased"] is False

    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member1"])},
                     headers=auth_headers(seed["member2"]))
    client.patch(f"/api/v1/death-reports/{r.json()['id']}/confirm", headers=auth_headers(seed["super_admin"]))

    r = client.get(f"/api/v1/collectes/{collecte_id}/contributions", headers=auth_headers(seed["super_admin"]))
    contribution = next(c for c in r.json() if c["id"] == contribution_id)
    assert contribution["member_deceased"] is True
