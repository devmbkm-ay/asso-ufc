from tests.conftest import auth_headers


def test_create_designation(client, seed):
    r = client.post(
        "/api/v1/beneficiaries/me",
        json={"full_name": "Tata Test", "relation": "tante", "contact": "0600000001"},
        headers=auth_headers(seed["member1"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["full_name"] == "Tata Test"
    assert body["status"] == "pending"
    assert body["member_id"] == str(seed["member1"])


def test_max_two_active_designations(client, seed):
    h = auth_headers(seed["member1"])
    for i in range(2):
        r = client.post("/api/v1/beneficiaries/me",
                         json={"full_name": f"Personne {i}", "relation": "ami", "contact": "0600000000"},
                         headers=h)
        assert r.status_code == 201

    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "Troisième", "relation": "ami", "contact": "0600000000"},
                     headers=h)
    assert r.status_code == 400


def test_revoked_designation_does_not_count_toward_max(client, seed):
    h = auth_headers(seed["member1"])
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "A", "relation": "ami", "contact": "0600000000"}, headers=h)
    d1 = r.json()["id"]
    client.post("/api/v1/beneficiaries/me",
                json={"full_name": "B", "relation": "ami", "contact": "0600000000"}, headers=h)

    r = client.delete(f"/api/v1/beneficiaries/me/{d1}", headers=h)
    assert r.status_code == 204

    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "C", "relation": "ami", "contact": "0600000000"}, headers=h)
    assert r.status_code == 201


def test_revoked_designation_excluded_from_my_list(client, seed):
    h = auth_headers(seed["member1"])
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "Revoke Me", "relation": "ami", "contact": "0600000000"}, headers=h)
    d1 = r.json()["id"]
    client.delete(f"/api/v1/beneficiaries/me/{d1}", headers=h)

    r = client.get("/api/v1/beneficiaries/me", headers=h)
    assert r.status_code == 200
    assert all(d["id"] != d1 for d in r.json())


def test_validate_designation_requires_admin_role(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]

    r = client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["member2"]))
    assert r.status_code == 403

    r = client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 403


def test_validate_designation_sets_grace_period(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]

    r = client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "validated"
    assert body["active_from"] is not None


def test_reject_designation(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]

    r = client.patch(f"/api/v1/beneficiaries/{designation_id}/reject", headers=auth_headers(seed["president"]))
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_cannot_validate_twice(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))

    r = client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 400


def test_admin_list_filters_by_member_id(client, seed):
    client.post("/api/v1/beneficiaries/me",
                json={"full_name": "Awa's beneficiary", "relation": "ami", "contact": "0600000000"},
                headers=auth_headers(seed["member1"]))
    client.post("/api/v1/beneficiaries/me",
                json={"full_name": "Brice's beneficiary", "relation": "ami", "contact": "0600000000"},
                headers=auth_headers(seed["member2"]))

    r = client.get("/api/v1/beneficiaries",
                    params={"member_id": str(seed["member1"])},
                    headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    names = [d["full_name"] for d in r.json()]
    assert names == ["Awa's beneficiary"]
