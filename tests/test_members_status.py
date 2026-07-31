from tests.conftest import auth_headers


def test_manual_status_change_requires_admin_role(client, seed):
    r = client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "deceased"},
                      headers=auth_headers(seed["member2"]))
    assert r.status_code == 403

    r = client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "deceased"},
                      headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 403


def test_admin_can_set_and_revert_deceased(client, seed):
    r = client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "deceased"},
                      headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    assert r.json()["status"] == "deceased"

    r = client.get("/api/v1/collectes", headers=auth_headers(seed["member1"]))
    assert r.status_code == 403

    r = client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "active"},
                      headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = client.get("/api/v1/collectes", headers=auth_headers(seed["member1"]))
    assert r.status_code == 200


def test_deceased_status_filter_on_list_members(client, seed):
    client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "deceased"},
                 headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/members", params={"status": "deceased"}, headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["items"]]
    assert str(seed["member1"]) in ids
    assert str(seed["member2"]) not in ids


def test_status_counts_requires_privileged_role(client, seed):
    r = client.get("/api/v1/members/status-counts", headers=auth_headers(seed["member1"]))
    assert r.status_code == 403

    r = client.get("/api/v1/members/status-counts", headers=auth_headers(seed["treasurer"]))
    assert r.status_code == 403

    r = client.get("/api/v1/members/status-counts", headers=auth_headers(seed["secretary"]))
    assert r.status_code == 200


def test_status_counts_reflects_seed_and_updates(client, seed):
    r = client.get("/api/v1/members/status-counts", headers=auth_headers(seed["super_admin"]))
    assert r.status_code == 200
    body = r.json()
    # 6 membres de seed, tous "active" au départ (cf. conftest.seed)
    assert body["active"] == 6
    assert body["deceased"] == 0

    client.patch(f"/api/v1/members/{seed['member1']}/status", json={"status": "deceased"},
                 headers=auth_headers(seed["super_admin"]))

    r = client.get("/api/v1/members/status-counts", headers=auth_headers(seed["super_admin"]))
    body = r.json()
    assert body["active"] == 5
    assert body["deceased"] == 1
