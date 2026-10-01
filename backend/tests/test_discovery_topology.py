from __future__ import annotations

import asyncio

import pytest

from netmon.models import DeviceType
from netmon.services.discovery import DiscoveryError, guess_device_type, parse_network
from tests.conftest import create_device


def test_parse_network_limits():
    assert len(parse_network("192.168.1.0/24", 1024)) == 254
    assert parse_network("10.0.0.7/32", 1024) == ["10.0.0.7"]
    with pytest.raises(DiscoveryError):
        parse_network("10.0.0.0/16", 1024)
    with pytest.raises(DiscoveryError):
        parse_network("not-a-network", 1024)
    with pytest.raises(DiscoveryError):
        parse_network("2001:db8::/120", 1024)


@pytest.mark.parametrize(
    ("descr", "ip", "expected"),
    [
        ("Cisco IOS Software, C2960X Software", "10.0.0.9", DeviceType.SWITCH),
        ("Cisco IOS Software, C2900 Software", "10.0.0.9", DeviceType.ROUTER),
        ("HP LaserJet Pro M404dn", "10.0.0.9", DeviceType.PRINTER),
        ("Linux web01 6.8.0", "10.0.0.9", DeviceType.SERVER),
        ("Hardware: x86 - Software: Windows", "10.0.0.9", DeviceType.PC),
        ("pfSense 2.7", "10.0.0.9", DeviceType.FIREWALL),
        (None, "10.0.0.1", DeviceType.ROUTER),
        (None, "10.0.0.9", DeviceType.OTHER),
    ],
)
def test_guess_device_type(descr, ip, expected):
    assert guess_device_type(descr, ip) == expected


async def wait_for_scan(client, headers, job_id):
    for _ in range(100):
        job = (await client.get(f"/discovery/scans/{job_id}", headers=headers)).json()
        if job["status"] not in ("pending", "running"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("scan did not finish")


async def test_discovery_scan_and_import(client, admin_headers, backend):
    await create_device(client, admin_headers, name="Known", ip_address="10.9.0.2")
    backend.alive = {"10.9.0.1", "10.9.0.2", "10.9.0.20"}
    resp = await client.post(
        "/discovery/scans",
        json={"cidr": "10.9.0.0/27", "snmp_community": "public"},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    job = await wait_for_scan(client, admin_headers, resp.json()["id"])
    assert job["status"] == "completed"
    assert job["scanned"] == job["total"] == 30
    assert [h["ip_address"] for h in job["hosts"]] == ["10.9.0.1", "10.9.0.2", "10.9.0.20"]
    known = next(h for h in job["hosts"] if h["ip_address"] == "10.9.0.2")
    assert known["existing_device_id"] is not None
    assert job["hosts"][0]["suggested_type"] == "switch"  # from the SNMP sysDescr

    resp = await client.post(
        "/discovery/import",
        json={
            "hosts": [
                {"ip_address": "10.9.0.1", "name": "Gateway", "device_type": "router"},
                {"ip_address": "10.9.0.2", "name": "Dup"},
                {"ip_address": "10.9.0.20", "name": "Known"},
            ]
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    result = resp.json()
    assert len(result["created"]) == 2 and result["skipped"] == ["10.9.0.2"]
    names = {
        d["name"] for d in (await client.get("/devices", headers=admin_headers)).json()["items"]
    }
    assert names == {"Known", "Gateway", "Known (10.9.0.20)"}


async def test_discovery_rejects_large_or_invalid_networks(client, admin_headers, viewer_headers):
    resp = await client.post("/discovery/scans", json={"cidr": "10.0.0.0/8"}, headers=admin_headers)
    assert resp.status_code == 422
    resp = await client.post(
        "/discovery/scans", json={"cidr": "10.0.0.0/24", "method": "tcp"}, headers=admin_headers
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/discovery/scans", json={"cidr": "10.0.0.0/24"}, headers=viewer_headers
    )
    assert resp.status_code == 403


async def test_topology_links_and_status(client, admin_headers, backend):
    router = await create_device(client, admin_headers)
    switch = await create_device(client, admin_headers, name="Switch", ip_address="10.0.0.2")
    resp = await client.post(
        "/topology/links",
        json={"source_id": router["id"], "target_id": switch["id"], "link_type": "fiber"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    link = resp.json()

    reverse = await client.post(
        "/topology/links",
        json={"source_id": switch["id"], "target_id": router["id"]},
        headers=admin_headers,
    )
    assert reverse.status_code == 409
    self_link = await client.post(
        "/topology/links",
        json={"source_id": switch["id"], "target_id": switch["id"]},
        headers=admin_headers,
    )
    assert self_link.status_code == 422

    topo = (await client.get("/topology", headers=admin_headers)).json()
    assert len(topo["nodes"]) == 2 and topo["edges"][0]["status"] == "unknown"

    for device in (router, switch):
        await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    topo = (await client.get("/topology", headers=admin_headers)).json()
    assert topo["edges"][0]["status"] == "up"

    resp = await client.put(
        "/topology/positions",
        json=[{"device_id": router["id"], "x": 10, "y": 20}],
        headers=admin_headers,
    )
    assert resp.status_code == 200
    topo = (await client.get("/topology", headers=admin_headers)).json()
    node = next(n for n in topo["nodes"] if n["id"] == router["id"])
    assert (node["x"], node["y"]) == (10, 20)

    resp = await client.patch(
        f"/topology/links/{link['id']}", json={"bandwidth_mbps": 1000}, headers=admin_headers
    )
    assert resp.json()["bandwidth_mbps"] == 1000
    assert (
        await client.delete(f"/topology/links/{link['id']}", headers=admin_headers)
    ).status_code == 204

    # Deleting a device removes its links (ON DELETE CASCADE).
    await client.post(
        "/topology/links",
        json={"source_id": router["id"], "target_id": switch["id"]},
        headers=admin_headers,
    )
    await client.delete(f"/devices/{switch['id']}", headers=admin_headers)
    topo = (await client.get("/topology", headers=admin_headers)).json()
    assert topo["edges"] == []


async def test_alert_rule_management(client, admin_headers, viewer_headers):
    rules = (await client.get("/alert-rules", headers=admin_headers)).json()
    assert {r["metric"] for r in rules} >= {"device_down", "cpu_percent", "packet_loss"}

    resp = await client.post(
        "/alert-rules",
        json={"name": "Slow WAN", "metric": "latency_ms", "threshold": 80,
              "device_type": "router", "severity": "info"},
        headers=admin_headers,
    )  # fmt: skip
    assert resp.status_code == 201
    rule = resp.json()
    both = await client.post(
        "/alert-rules",
        json={"name": "x", "metric": "latency_ms", "device_type": "router", "device_id": 1},
        headers=admin_headers,
    )
    assert both.status_code == 422
    assert (
        await client.post("/alert-rules", json={"name": "x", "metric": "cpu_percent"},
                          headers=viewer_headers)
    ).status_code == 403  # fmt: skip

    resp = await client.patch(
        f"/alert-rules/{rule['id']}", json={"threshold": 120, "enabled": False},
        headers=admin_headers,
    )  # fmt: skip
    assert resp.json()["threshold"] == 120 and resp.json()["enabled"] is False
    assert (
        await client.delete(f"/alert-rules/{rule['id']}", headers=admin_headers)
    ).status_code == 204
