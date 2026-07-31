from tests.conftest import auth_headers


def test_plain_member_sees_all_zero(client, seed):
    r = client.get("/api/v1/admin/pending-counts", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200
    assert r.json() == {"beneficiaries": 0, "death_reports": 0, "cotisations": 0, "collectes": 0}


def test_super_admin_sees_pending_designation_and_report(client, seed):
    client.post("/api/v1/beneficiaries/me",
                json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                headers=auth_headers(seed["member1"]))
    client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                headers=auth_headers(seed["member1"]))

    r = client.get("/api/v1/admin/pending-counts", headers=auth_headers(seed["super_admin"]))
    body = r.json()
    assert body["beneficiaries"] == 1
    assert body["death_reports"] == 1


def test_treasurer_only_sees_payment_domains(client, seed):
    client.post("/api/v1/beneficiaries/me",
                json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                headers=auth_headers(seed["member1"]))

    r = client.get("/api/v1/admin/pending-counts", headers=auth_headers(seed["treasurer"]))
    body = r.json()
    assert body["beneficiaries"] == 0
    assert body["death_reports"] == 0
    assert "cotisations" in body
    assert "collectes" in body


def test_count_returns_to_zero_after_resolution(client, seed):
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]

    r = client.get("/api/v1/admin/pending-counts", headers=auth_headers(seed["super_admin"]))
    assert r.json()["death_reports"] == 1

    client.patch(f"/api/v1/death-reports/{report_id}/dismiss", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/admin/pending-counts", headers=auth_headers(seed["super_admin"]))
    assert r.json()["death_reports"] == 0
