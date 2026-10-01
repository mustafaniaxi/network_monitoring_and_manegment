"""End-to-end tests of the poll pipeline (probe -> SNMP -> persist -> alerts -> events)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from netmon.models import Alert, AlertStatus, Interface, MetricSample
from netmon.services.monitoring.types import InterfaceCounters, ProbeResult, SnmpSnapshot
from tests.conftest import create_device, down, up


def snmp_snapshot(in_octets: int, out_octets: int, cpu: float = 20.0) -> SnmpSnapshot:
    return SnmpSnapshot(
        sys_name="core-rtr",
        sys_descr="Cisco IOS",
        uptime_seconds=1000,
        cpu_percent=cpu,
        memory_percent=40.0,
        interfaces=[
            InterfaceCounters(if_index=1, name="lo", if_type=24, oper_status="up",
                              admin_status="up", speed_mbps=10, in_octets=5, out_octets=5,
                              counters_64bit=True),
            InterfaceCounters(if_index=2, name="Gi0/0", if_type=6, oper_status="up",
                              admin_status="up", speed_mbps=100, in_octets=in_octets,
                              out_octets=out_octets, counters_64bit=True),
        ],
        requests=4,
    )  # fmt: skip


async def test_successful_poll_records_sample_and_status(client, admin_headers, monitor, session):
    device = await create_device(client, admin_headers)
    resp = await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "up"
    assert body["last_latency_ms"] == 1.0
    assert body["last_seen_at"] is not None

    samples = (await session.scalars(select(MetricSample))).all()
    assert len(samples) == 1 and samples[0].is_up
    assert monitor.stats.polls_total == 1
    assert monitor.stats.probe_packets == 3


async def test_device_goes_down_alerts_and_recovers(client, admin_headers, backend, session):
    device = await create_device(client, admin_headers, name="Database Server")
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)

    backend.probes["10.0.0.1"] = down()
    first = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    # One failure is not enough (down_after_failures=2) - avoids flapping on a lost packet.
    assert first["status"] == "up"
    assert first["consecutive_failures"] == 1
    second = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    assert second["status"] == "down"

    alerts = (await client.get("/alerts", headers=admin_headers)).json()["items"]
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["message"] == "ALERT: Database Server is unreachable."
    assert alert["severity"] == "critical"
    assert alert["status"] == "active"
    assert alert["first_breach_at"] < alert["triggered_at"]

    # Further failures do not duplicate the alert.
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    assert (await client.get("/alerts", headers=admin_headers)).json()["total"] == 1

    backend.probes["10.0.0.1"] = up()
    recovered = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    assert recovered["status"] == "up"
    alert = (await client.get("/alerts", headers=admin_headers)).json()["items"][0]
    assert alert["status"] == "resolved"
    assert alert["resolution_note"] == "RESOLVED: Database Server is reachable again."


async def test_degraded_status_on_packet_loss(client, admin_headers, backend):
    device = await create_device(client, admin_headers)
    backend.probes["10.0.0.1"] = up(latency=2.0, loss=33.3)
    body = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    assert body["status"] == "degraded"


async def test_snmp_metrics_and_interface_rates(client, admin_headers, backend, session):
    device = await create_device(client, admin_headers, snmp_enabled=True, snmp_community="public")
    backend.snmp["10.0.0.1"] = snmp_snapshot(1_000_000, 2_000_000, cpu=35.5)
    body = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    assert body["last_cpu_percent"] == 35.5
    assert body["sys_name"] == "core-rtr"
    assert body["last_in_bps"] is None  # first reading - no rate yet

    # Pretend the previous reading was taken 10 s ago, then add 12.5 MB in / 2.5 MB out.
    for iface in (await session.scalars(select(Interface))).all():
        iface.counters_at -= timedelta(seconds=10)
    await session.commit()
    backend.snmp["10.0.0.1"] = snmp_snapshot(13_500_000, 4_500_000)
    body = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()

    assert round(body["last_in_bps"] / 1e6) == 10  # 12.5 MB * 8 / 10 s = 10 Mbit/s
    assert round(body["last_out_bps"] / 1e6) == 2
    # 10 Mbit/s on a 100 Mbit/s port (elapsed is 10 s plus a few ms of test runtime)
    assert body["last_bandwidth_util"] == pytest.approx(10.0, abs=0.2)

    ifaces = (await client.get(f"/devices/{device['id']}/interfaces", headers=admin_headers)).json()
    assert [i["name"] for i in ifaces] == ["lo", "Gi0/0"]
    assert ifaces[1]["utilization_percent"] == pytest.approx(10.0, abs=0.2)


async def test_snmp_failure_does_not_fail_poll(client, admin_headers):
    device = await create_device(client, admin_headers, snmp_enabled=True)
    body = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    assert body["status"] == "up"
    assert body["last_error"].startswith("SNMP:")


async def test_threshold_alert_respects_consecutive_and_resolves(
    client, admin_headers, backend, session
):
    device = await create_device(client, admin_headers, snmp_enabled=True)
    # Default "High CPU" rule: > 90 % on 2 consecutive samples.
    backend.snmp["10.0.0.1"] = snmp_snapshot(0, 0, cpu=97.0)
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    assert (await client.get("/alerts", headers=admin_headers)).json()["total"] == 0
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    alerts = (await client.get("/alerts", headers=admin_headers)).json()["items"]
    assert len(alerts) == 1
    assert alerts[0]["metric"] == "cpu_percent"
    assert "CPU utilisation is 97.0%" in alerts[0]["message"]

    backend.snmp["10.0.0.1"] = snmp_snapshot(0, 0, cpu=30.0)
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    alert = (await session.scalars(select(Alert))).one()
    assert alert.status == AlertStatus.RESOLVED


async def test_alert_acknowledge_and_manual_resolve(client, admin_headers, viewer_headers, backend):
    device = await create_device(client, admin_headers)
    backend.probes["10.0.0.1"] = down()
    for _ in range(2):
        await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    alert_id = (await client.get("/alerts", headers=admin_headers)).json()["items"][0]["id"]

    forbidden = await client.post(
        f"/alerts/{alert_id}/acknowledge", json={}, headers=viewer_headers
    )
    assert forbidden.status_code == 403
    ack = await client.post(
        f"/alerts/{alert_id}/acknowledge", json={"note": "on it"}, headers=admin_headers
    )
    assert ack.json()["status"] == "acknowledged"
    again = await client.post(f"/alerts/{alert_id}/acknowledge", json={}, headers=admin_headers)
    assert again.status_code == 409

    summary = (await client.get("/alerts/summary", headers=admin_headers)).json()
    assert summary["acknowledged"] == 1 and summary["by_severity"]["critical"] == 1

    res = await client.post(f"/alerts/{alert_id}/resolve", json={}, headers=admin_headers)
    assert res.json()["status"] == "resolved"
    assert res.json()["resolution_note"].startswith("Resolved manually")


async def test_poll_publishes_live_events(app, client, admin_headers, backend):
    device = await create_device(client, admin_headers)
    hub = app.state.hub
    async with hub.subscribe() as queue:
        backend.probes["10.0.0.1"] = down()
        for _ in range(2):
            await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
        events = [queue.get_nowait()["type"] for _ in range(queue.qsize())]
    assert events.count("device.sample") == 2
    assert "device.status" in events
    assert "alert.opened" in events


async def test_scheduler_polls_due_devices(app, client, admin_headers, backend, monitor):
    await create_device(client, admin_headers)
    await create_device(client, admin_headers, name="Switch", ip_address="10.0.0.2")
    monitor._next_due.clear()
    monitor.invalidate()
    await monitor._tick()  # schedules first polls (spread over a few seconds)
    for device_id in list(monitor._next_due):
        monitor._next_due[device_id] = 0
    await monitor._tick()
    while monitor.in_flight:
        await next(iter(monitor._in_flight.values()))
    assert sorted(backend.calls) == ["10.0.0.1", "10.0.0.2"]


async def test_retention_removes_old_samples(client, admin_headers, monitor, session):
    device = await create_device(client, admin_headers)
    await client.post(f"/devices/{device['id']}/check", headers=admin_headers)
    for sample in (await session.scalars(select(MetricSample))).all():
        sample.ts -= timedelta(days=400)
    await session.commit()
    removed = await monitor.apply_retention()
    assert removed == 1


async def test_tcp_probe_result_used_for_tcp_devices(client, admin_headers, backend):
    device = await create_device(client, admin_headers, check_method="tcp", tcp_port=443)
    backend.probes["10.0.0.1"] = ProbeResult(is_up=True, latency_ms=4.2, packet_loss=0,
                                             packets_sent=3)  # fmt: skip
    body = (await client.post(f"/devices/{device['id']}/check", headers=admin_headers)).json()
    assert body["last_latency_ms"] == 4.2
