from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from netmon.main import create_app
from netmon.models import CheckMethod, DeviceType
from netmon.services.monitoring.simulation import SimulatedBackend, diurnal_factor
from netmon.services.monitoring.types import DeviceTarget, SnmpCredentials
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, FakeBackend, create_device


async def test_health_and_metrics(app, client, admin_headers):
    base = "http://test"
    live = await client.get(f"{base}/health/live")
    assert live.json() == {"status": "ok"}
    ready = await client.get(f"{base}/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "ok", "monitoring": "disabled"}
    assert ready.headers["X-Content-Type-Options"] == "nosniff"

    device = await create_device(client, admin_headers)
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    metrics = await client.get(f"{base}/metrics")
    assert 'netmon_device_up{device="Core Router",type="router"} 1.0' in metrics.text


async def test_openapi_schema(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/v1/devices" in paths and "/api/v1/reports/availability" in paths


async def test_system_endpoints(client, admin_headers):
    info = (await client.get("/system/info", headers=admin_headers)).json()
    assert info["monitor_mode"] == "live"
    assert info["notifications"] == {"webhook": False, "email": False}
    stats = (await client.get("/system/stats", headers=admin_headers)).json()
    assert stats["backend"] == "fake"
    assert stats["process"]["rss_bytes"] > 0


def test_websocket_stream(settings):
    backend = FakeBackend()
    app = create_app(settings, backend=backend)
    with TestClient(app) as tc:
        token = tc.post(
            "/api/v1/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        device = tc.post(
            "/api/v1/devices", json={"name": "R1", "ip_address": "10.1.1.1"}, headers=headers
        ).json()
        with tc.websocket_connect(f"/api/v1/ws?token={token}") as ws:
            assert ws.receive_json()["type"] == "hello"
            tc.post(f"/api/v1/devices/{device['id']}/check", headers=headers)
            events = [ws.receive_json()["type"] for _ in range(2)]
            assert "device.sample" in events

        with (
            pytest.raises(WebSocketDisconnect) as refused,
            tc.websocket_connect("/api/v1/ws?token=garbage") as ws,
        ):
            ws.receive_json()
        assert refused.value.code == 1008


def target(device_id: int, name: str, device_type: DeviceType) -> DeviceTarget:
    return DeviceTarget(id=device_id, name=name, host=f"10.0.0.{device_id}",
                        device_type=device_type, check_method=CheckMethod.ICMP,
                        snmp=SnmpCredentials())  # fmt: skip


async def test_simulated_backend_produces_plausible_data():
    sim = SimulatedBackend(seed=42)
    router = target(1, "Edge Router", DeviceType.ROUTER)
    results = [await sim.probe(router) for _ in range(50)]
    up = [r for r in results if r.is_up]
    assert len(up) >= 40
    assert all(0 < (r.latency_ms or 0) < 200 for r in up)

    snap = await sim.snmp_poll(router)
    assert 0 <= (snap.cpu_percent or 0) <= 100
    assert snap.interfaces and snap.interfaces[0].counters_64bit
    before = snap.interfaces[0].in_octets
    snap2 = await sim.snmp_poll(router)
    assert snap2.interfaces[0].in_octets >= before

    flaky = target(2, "Database Server", DeviceType.SERVER)
    outages = 0
    for _ in range(400):
        outages += not (await sim.probe(flaky)).is_up
    assert outages > 0  # the demo database server misbehaves on purpose


async def test_simulated_discovery_is_deterministic():
    a, b = SimulatedBackend(seed=1), SimulatedBackend(seed=1)
    hosts = [f"10.0.0.{i}" for i in range(1, 60)]
    alive_a = [h for h in hosts if (await a.discover(h, CheckMethod.ICMP, None)).is_up]
    alive_b = [h for h in hosts if (await b.discover(h, CheckMethod.ICMP, None)).is_up]
    assert alive_a == alive_b and "10.0.0.1" in alive_a
    info = await a.snmp_system("10.0.0.1", SnmpCredentials())
    assert "Cisco" in str(info["sys_descr"])


def test_diurnal_factor_bounds():
    from datetime import datetime

    assert diurnal_factor(datetime(2026, 3, 4, 3, 0)) == 0.15
    assert diurnal_factor(datetime(2026, 3, 4, 13, 0)) > 0.9
    assert diurnal_factor(datetime(2026, 3, 7, 13, 0)) < 0.6  # Saturday
