from tests.conftest import auth_headers


def _make_designation(client, seed, owner_key="member1"):
    r = client.post(
        "/api/v1/beneficiaries/me",
        json={"full_name": "Tante Test", "relation": "tante", "contact": "0600000000"},
        headers=auth_headers(seed[owner_key]),
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_sens_a_create(client, seed):
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                     headers=auth_headers(seed["member1"]))
    assert r.status_code == 201
    assert r.json()["member_id"] == str(seed["member2"])
    assert r.json()["designation_id"] is None


def test_sens_a_self_report_blocked(client, seed):
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member1"])},
                     headers=auth_headers(seed["member1"]))
    assert r.status_code == 400


def test_sens_a_duplicate_pending_guard(client, seed):
    h = auth_headers(seed["member1"])
    client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])}, headers=h)
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])}, headers=h)
    assert r.status_code == 409


def test_sens_b_reserved_to_designator_or_admin(client, seed):
    designation_id = _make_designation(client, seed, "member1")

    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id},
                     headers=auth_headers(seed["member2"]))
    assert r.status_code == 403

    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id},
                     headers=auth_headers(seed["member1"]))
    assert r.status_code == 201


def test_sens_b_allowed_for_admin_on_behalf_of_designator(client, seed):
    designation_id = _make_designation(client, seed, "member1")
    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id},
                     headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 201


def test_sens_b_duplicate_pending_guard(client, seed):
    designation_id = _make_designation(client, seed, "member1")
    h = auth_headers(seed["member1"])
    client.post("/api/v1/death-reports", json={"designation_id": designation_id}, headers=h)
    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id}, headers=h)
    assert r.status_code == 409


def test_plain_member_cannot_list_or_confirm(client, seed):
    r = client.get("/api/v1/death-reports", headers=auth_headers(seed["member1"]))
    assert r.status_code == 403

    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]
    r = client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["member1"]))
    assert r.status_code == 403


def test_confirm_sens_a_marks_member_deceased(client, seed):
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]

    r = client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200

    r = client.get("/api/v1/members", params={"status": "deceased"}, headers=auth_headers(seed["super_admin"]))
    assert any(m["id"] == str(seed["member2"]) for m in r.json()["items"])

    # Le membre décédé ne peut plus s'authentifier
    r = client.get("/api/v1/collectes", headers=auth_headers(seed["member2"]))
    assert r.status_code == 403


def test_confirm_sens_b_does_not_change_designator_status(client, seed):
    designation_id = _make_designation(client, seed, "member1")
    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]

    r = client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200

    r = client.get("/api/v1/members", params={"status": "deceased"}, headers=auth_headers(seed["super_admin"]))
    assert all(m["id"] != str(seed["member1"]) for m in r.json()["items"])

    r = client.get("/api/v1/collectes", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200


def test_dismiss_report(client, seed):
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]

    r = client.patch(f"/api/v1/death-reports/{report_id}/dismiss", headers=auth_headers(seed["president"]))
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"

    # Le membre n'est pas marqué décédé sur un rejet
    r = client.get("/api/v1/members", params={"status": "deceased"}, headers=auth_headers(seed["super_admin"]))
    assert all(m["id"] != str(seed["member2"]) for m in r.json()["items"])


def test_cannot_confirm_already_confirmed_report(client, seed):
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]
    client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["super_admin"]))

    r = client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 400


def test_new_report_allowed_after_dismiss(client, seed):
    h = auth_headers(seed["member1"])
    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])}, headers=h)
    report_id = r.json()["id"]
    client.patch(f"/api/v1/death-reports/{report_id}/dismiss", headers=auth_headers(seed["super_admin"]))

    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member2"])}, headers=h)
    assert r.status_code == 201


def test_confirmed_sens_b_flags_person_deceased_on_designation(client, seed):
    designation_id = _make_designation(client, seed, "member1")

    r = client.get("/api/v1/beneficiaries", headers=auth_headers(seed["super_admin"]))
    before = next(d for d in r.json() if d["id"] == designation_id)
    assert before["person_deceased"] is False

    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]
    client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/beneficiaries", headers=auth_headers(seed["super_admin"]))
    after = next(d for d in r.json() if d["id"] == designation_id)
    assert after["person_deceased"] is True


def test_dismissed_sens_b_does_not_flag_person_deceased(client, seed):
    designation_id = _make_designation(client, seed, "member1")
    r = client.post("/api/v1/death-reports", json={"designation_id": designation_id},
                     headers=auth_headers(seed["member1"]))
    report_id = r.json()["id"]
    client.patch(f"/api/v1/death-reports/{report_id}/dismiss", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/beneficiaries", headers=auth_headers(seed["super_admin"]))
    designation = next(d for d in r.json() if d["id"] == designation_id)
    assert designation["person_deceased"] is False


def test_confirmed_sens_a_flags_member_deceased_on_their_own_designations(client, seed):
    designation_id = _make_designation(client, seed, "member1")

    r = client.post("/api/v1/death-reports", json={"member_id": str(seed["member1"])},
                     headers=auth_headers(seed["member2"]))
    report_id = r.json()["id"]
    client.patch(f"/api/v1/death-reports/{report_id}/confirm", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/beneficiaries", headers=auth_headers(seed["super_admin"]))
    designation = next(d for d in r.json() if d["id"] == designation_id)
    assert designation["member_deceased"] is True
    assert designation["person_deceased"] is False
