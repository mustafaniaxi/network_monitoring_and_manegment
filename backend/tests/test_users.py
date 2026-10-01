from __future__ import annotations


async def test_user_lifecycle(client, admin_headers):
    resp = await client.post(
        "/users",
        json={"email": "Ops@Example.com", "password": "password-123", "role": "operator"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    user = resp.json()
    assert user["email"] == "ops@example.com"
    assert "hashed_password" not in user

    dup = await client.post(
        "/users",
        json={"email": "ops@example.com", "password": "password-123"},
        headers=admin_headers,
    )
    assert dup.status_code == 409

    resp = await client.patch(
        f"/users/{user['id']}", json={"role": "viewer", "is_active": False}, headers=admin_headers
    )
    assert resp.json()["role"] == "viewer"
    assert resp.json()["is_active"] is False

    # Deactivated users cannot sign in.
    login = await client.post(
        "/auth/login", data={"username": "ops@example.com", "password": "password-123"}
    )
    assert login.status_code == 401

    assert (await client.delete(f"/users/{user['id']}", headers=admin_headers)).status_code == 204
    users = (await client.get("/users", headers=admin_headers)).json()
    assert [u["email"] for u in users] == ["admin@test.local"]


async def test_invalid_email_and_short_password_rejected(client, admin_headers):
    resp = await client.post(
        "/users", json={"email": "not-an-email", "password": "password-123"}, headers=admin_headers
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/users", json={"email": "a@b.lan", "password": "short"}, headers=admin_headers
    )
    assert resp.status_code == 422


async def test_last_admin_is_protected(client, admin_headers):
    me = (await client.get("/auth/me", headers=admin_headers)).json()
    assert (await client.delete(f"/users/{me['id']}", headers=admin_headers)).status_code == 409
    resp = await client.patch(f"/users/{me['id']}", json={"role": "viewer"}, headers=admin_headers)
    assert resp.status_code == 409
