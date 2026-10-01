"""Historical analysis: bucketing, availability/downtime maths and reports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from netmon.models import (
    Alert,
    AlertMetric,
    AlertSeverity,
    AlertStatus,
    Device,
    DeviceType,
    Interface,
    MetricSample,
)
from netmon.services import analytics
from netmon.services.analytics import Window

NOW = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)  # a Wednesday


async def seed(session) -> tuple[Device, Device]:
    a = Device(name="Router", ip_address="10.0.0.1", device_type=DeviceType.ROUTER)
    b = Device(name="Server", ip_address="10.0.0.10", device_type=DeviceType.SERVER)
    session.add_all([a, b])
    await session.flush()
    # 60 one-minute samples for the router: 6 down, latency 10 ms in the first half, 30 ms after.
    for i in range(60):
        ts = NOW - timedelta(minutes=60 - i)
        is_up = not (30 <= i < 36)
        session.add(
            MetricSample(
                device_id=a.id, ts=ts, is_up=is_up,
                latency_ms=(10.0 if i < 30 else 30.0) if is_up else None,
                latency_max_ms=40.0 if is_up else None,
                packet_loss=0.0 if is_up else 100.0,
                in_bps=1_000_000.0, out_bps=500_000.0, bandwidth_util=1.5,
                cpu_percent=50.0,
            )
        )  # fmt: skip
        session.add(MetricSample(device_id=b.id, ts=ts, is_up=True, latency_ms=2.0,
                                 packet_loss=0.0, in_bps=2_000_000.0, out_bps=0.0))  # fmt: skip
    session.add(
        Alert(
            device_id=a.id, metric=AlertMetric.DEVICE_DOWN, severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED, title="Device unreachable",
            message="ALERT: Router is unreachable.",
            first_breach_at=NOW - timedelta(minutes=30),
            triggered_at=NOW - timedelta(minutes=29),
            resolved_at=NOW - timedelta(minutes=24),
        )
    )  # fmt: skip
    session.add(Interface(device_id=a.id, if_index=1, name="Gi0/0", utilization_percent=72.5))
    await session.commit()
    return a, b


def test_window_bucket_starts_are_aligned():
    window = Window.from_range("1h", now=NOW)
    starts = window.bucket_starts()
    assert window.bucket_seconds == 60
    assert all(s % 60 == 0 for s in starts)
    assert len(starts) == 61


async def test_device_series_buckets_and_availability(session):
    router, _ = await seed(session)
    window = Window.from_range("1h", now=NOW)
    points = await analytics.device_series(session, router.id, window)
    assert len(points) == len(window.bucket_starts())
    populated = [p for p in points if p["samples"]]
    assert len(populated) == 60
    assert sum(1 for p in populated if p["availability"] == 0.0) == 6
    assert populated[0]["latency_ms"] == 10.0
    assert populated[-1]["latency_ms"] == 30.0
    assert populated[0]["in_bps"] == 1_000_000


async def test_network_series_sums_throughput(session):
    await seed(session)
    window = Window(start=NOW - timedelta(hours=1), end=NOW, bucket_seconds=3600)
    points = [p for p in await analytics.network_series(session, window) if p["devices"]]
    assert sum(p["in_bps"] for p in points) > 0
    assert all(p["devices"] == 2 for p in points)


async def test_availability_report(session):
    await seed(session)
    window = Window(start=NOW - timedelta(hours=2), end=NOW, bucket_seconds=300)
    rows = {r["name"]: r for r in await analytics.availability_report(session, window)}
    r = rows["Router"]
    assert r["samples"] == 60
    assert r["availability"] == pytest.approx(90.0)
    assert r["incidents"] == 1
    assert r["downtime_seconds"] == 6 * 60
    assert r["mttr_seconds"] == 6 * 60
    assert rows["Server"]["availability"] == 100.0
    assert rows["Server"]["incidents"] == 0

    failing = await analytics.top_failing(session, window)
    assert [f["name"] for f in failing] == ["Router"]


async def test_degradation_flags_latency_increase(session):
    await seed(session)
    window = Window(start=NOW - timedelta(minutes=60), end=NOW, bucket_seconds=60)
    rows = {r["name"]: r for r in await analytics.degradation(session, window)}
    assert rows["Router"]["degraded"] is True
    assert rows["Router"]["latency_change_percent"] == 200.0
    assert rows["Server"]["degraded"] is False


async def test_traffic_heatmap_and_bottlenecks(session):
    await seed(session)
    window = Window(start=NOW - timedelta(hours=2), end=NOW, bucket_seconds=3600)
    heatmap = await analytics.traffic_heatmap(session, window)
    assert heatmap["peak"]["day"] == 2  # Wednesday
    assert heatmap["peak"]["hour"] == 11
    assert len(heatmap["matrix_bps"]) == 7 and len(heatmap["matrix_bps"][0]) == 24

    shifted = await analytics.traffic_heatmap(session, window, tz_offset_minutes=180)
    assert shifted["peak"]["hour"] == 14

    result = await analytics.bottlenecks(session, window)
    assert result["devices"][0]["name"] == "Router"
    assert result["interfaces"][0]["utilization_percent"] == 72.5


async def test_detection_report(session):
    await seed(session)
    window = Window(start=NOW - timedelta(hours=2), end=NOW, bucket_seconds=300)
    report = await analytics.detection_report(session, window)
    assert report["outages"] == 1
    assert report["detection_delay_seconds"]["mean"] == 60.0
    assert report["time_to_recovery_seconds"]["mean"] == 360.0


async def test_report_endpoints(client, admin_headers, session):
    await seed(session)
    for path in (
        "/dashboard/summary", "/dashboard/timeseries?range=24h", "/reports/availability",
        "/reports/top-failing", "/reports/traffic-heatmap?tz_offset_minutes=60",
        "/reports/bottlenecks", "/reports/degradation", "/reports/detection",
    ):  # fmt: skip
        resp = await client.get(path, headers=admin_headers)
        assert resp.status_code == 200, (path, resp.text)

    csv_resp = await client.get("/reports/availability.csv?range=30d", headers=admin_headers)
    assert csv_resp.headers["content-type"].startswith("text/csv")
    lines = csv_resp.text.strip().splitlines()
    assert lines[0].startswith("device_id,name,ip_address")
    assert len(lines) == 3

    samples = await client.get("/reports/samples.csv?range=30d", headers=admin_headers)
    assert samples.status_code == 200
    assert samples.text.splitlines()[0].startswith("ts,device_id,device")

    bad = await client.get("/reports/availability?range=2y", headers=admin_headers)
    assert bad.status_code == 422
