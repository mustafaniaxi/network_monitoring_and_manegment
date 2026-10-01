from __future__ import annotations

import pytest

from tests.conftest import create_device


async def test_device_crud(client, admin_headers):
    device = await create_device(
        client, admin_headers, snmp_enabled=True, snmp_community="s3cret", tags=["Core", " wan "]
    )
    assert device["status"] == "unknown"
    assert device["tags"] == ["core", "wan"]
    # Secrets are write-only.
    assert "snmp_community" not in device
    assert device["snmp_community_set"] is True

    resp = await client.patch(
        f"/devices/{device['id']}",
        json={"location": "Rack A", "snmp_community": ""},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["location"] == "Rack A"
    assert resp.json()["snmp_community_set"] is False

    resp = await client.get(f"/devices/{device['id']}", headers=admin_headers)
    assert resp.json()["name"] == "Core Router"

    assert (
        await client.delete(f"/devices/{device['id']}", headers=admin_headers)
    ).status_code == 204
    assert (await client.get(f"/devices/{device['id']}", headers=admin_headers)).status_code == 404


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"name": "a", "ip_address": "300.1.1.1"}, 422),
        ({"name": "a", "ip_address": "bad host!"}, 422),
        ({"name": "a", "ip_address": "10.0.0.5", "check_method": "tcp"}, 422),
        ({"name": "a", "ip_address": "10.0.0.5", "poll_interval_seconds": 1}, 422),
        ({"name": "a", "ip_address": "fe80::1"}, 201),
        ({"name": "a", "ip_address": "printer.office.lan"}, 201),
        ({"name": "a", "ip_address": "10.0.0.5", "check_method": "tcp", "tcp_port": 443}, 201),
    ],
)
async def test_device_validation(client, admin_headers, payload, expected):
    resp = await client.post("/devices", json=payload, headers=admin_headers)
    assert resp.status_code == expected, resp.text


async def test_duplicate_name_or_address_conflicts(client, admin_headers):
    await create_device(client, admin_headers)
    resp = await client.post(
        "/devices", json={"name": "core router", "ip_address": "10.0.0.2"}, headers=admin_headers
    )
    assert resp.status_code == 409
    resp = await client.post(
        "/devices", json={"name": "Other", "ip_address": "10.0.0.1"}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_list_filters_search_and_pagination(client, admin_headers):
    for i in range(5):
        await create_device(
            client, admin_headers, name=f"Server {i}", ip_address=f"10.0.1.{i + 1}",
            device_type="server", location="DC-1" if i % 2 else "DC-2",
        )  # fmt: skip
    await create_device(client, admin_headers, name="Edge", ip_address="10.0.0.1")

    page = (await client.get("/devices?page_size=2&page=2", headers=admin_headers)).json()
    assert page["total"] == 6 and len(page["items"]) == 2 and page["page"] == 2

    servers = (await client.get("/devices?device_type=server", headers=admin_headers)).json()
    assert servers["total"] == 5
    found = (await client.get("/devices?search=dc-1", headers=admin_headers)).json()
    assert found["total"] == 2
    ordered = (await client.get("/devices?sort=-name", headers=admin_headers)).json()
    assert ordered["items"][0]["name"] == "Server 4"
    bad = await client.get("/devices?sort=hashed_password", headers=admin_headers)
    assert bad.status_code == 422


async def test_disabling_monitoring_resolves_alerts(client, admin_headers, monitor, backend):
    from tests.conftest import down

    device = await create_device(client, admin_headers)
    backend.probes["10.0.0.1"] = down()
    for _ in range(2):
        await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    alerts = (await client.get("/alerts?open_only=true", headers=admin_headers)).json()
    assert alerts["total"] == 1

    resp = await client.patch(
        f"/devices/{device['id']}", json={"is_monitored": False}, headers=admin_headers
    )
    assert resp.json()["status"] == "unknown"
    alerts = (await client.get("/alerts?open_only=true", headers=admin_headers)).json()
    assert alerts["total"] == 0
