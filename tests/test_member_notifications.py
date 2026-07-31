from tests.conftest import auth_headers


def test_notification_created_on_designation_validated(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "Tata Test", "relation": "tante", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200
    notif = next((n for n in r.json() if n["type"] == "designation_validated"), None)
    assert notif is not None
    assert "Tata Test" in notif["message"]
    assert notif["read"] is False
    assert notif["link"] == "/mon-espace/beneficiaires"


def test_notifications_are_isolated_between_members(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    client.patch(f"/api/v1/beneficiaries/{designation_id}/reject", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member2"]))
    assert r.status_code == 200
    assert all(n["type"] != "designation_rejected" for n in r.json())


def test_mark_single_notification_read(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    notif_id = r.json()[0]["id"]

    r = client.patch(f"/api/v1/notifications/me/{notif_id}/read", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200
    assert r.json()["read"] is True


def test_cannot_mark_someone_elses_notification_read(client, seed):
    r = client.post("/api/v1/beneficiaries/me",
                     json={"full_name": "X", "relation": "ami", "contact": "0600000000"},
                     headers=auth_headers(seed["member1"]))
    designation_id = r.json()["id"]
    client.patch(f"/api/v1/beneficiaries/{designation_id}/validate", headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/notifications/me", headers=auth_headers(seed["member1"]))
    notif_id = r.json()[0]["id"]

    r = client.patch(f"/api/v1/notifications/me/{notif_id}/read", headers=auth_headers(seed["member2"]))
    assert r.status_code == 404


def test_mark_all_read(client, seed):
    h = auth_headers(seed["member1"])
    for full_name in ["A", "B"]:
        r = client.post("/api/v1/beneficiaries/me",
                         json={"full_name": full_name, "relation": "ami", "contact": "0600000000"}, headers=h)
        client.patch(f"/api/v1/beneficiaries/{r.json()['id']}/validate", headers=auth_headers(seed["super_admin"]))

    r = client.post("/api/v1/notifications/me/read-all", headers=h)
    assert r.status_code == 204

    r = client.get("/api/v1/notifications/me", headers=h)
    assert all(n["read"] is True for n in r.json())
