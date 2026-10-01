from __future__ import annotations

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login


async def test_login_returns_token_and_user(client):
    resp = await client.post(
        "/auth/login", data={"username": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "admin"
    assert body["expires_in"] > 0


async def test_login_rejects_bad_password(client):
    resp = await client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": "nope"})
    assert resp.status_code == 401


async def test_login_rejects_unknown_user(client):
    resp = await client.post("/auth/login", data={"username": "x@y.z", "password": "whatever1"})
    assert resp.status_code == 401


async def test_login_is_throttled_after_repeated_failures(client):
    for _ in range(3):
        await client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": "bad"})
    resp = await client.post(
        "/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


async def test_protected_endpoints_require_token(client):
    assert (await client.get("/devices")).status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    assert (await client.get("/devices", headers=bad)).status_code == 401


async def test_me_and_profile_update(client, admin_headers):
    me = await client.get("/auth/me", headers=admin_headers)
    assert me.json()["email"] == ADMIN_EMAIL
    resp = await client.patch("/auth/me", json={"full_name": "Net Admin"}, headers=admin_headers)
    assert resp.json()["full_name"] == "Net Admin"


async def test_change_password_revokes_existing_tokens(client, admin_headers):
    resp = await client.post(
        "/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "new-password-1"},
        headers=admin_headers,
    )
    assert resp.status_code == 400

    resp = await client.post(
        "/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "new-password-1"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    # The old token was bound to the previous password hash.
    assert (await client.get("/auth/me", headers=admin_headers)).status_code == 401
    new_headers = await login(client, ADMIN_EMAIL, "new-password-1")
    assert (await client.get("/auth/me", headers=new_headers)).status_code == 200


async def test_viewer_is_read_only(client, viewer_headers):
    assert (await client.get("/devices", headers=viewer_headers)).status_code == 200
    resp = await client.post(
        "/devices", json={"name": "x", "ip_address": "10.0.0.9"}, headers=viewer_headers
    )
    assert resp.status_code == 403
    assert (await client.get("/users", headers=viewer_headers)).status_code == 403


async def test_operator_manages_devices_but_not_users(client, operator_headers):
    resp = await client.post(
        "/devices", json={"name": "x", "ip_address": "10.0.0.9"}, headers=operator_headers
    )
    assert resp.status_code == 201
    assert (await client.get("/users", headers=operator_headers)).status_code == 403
