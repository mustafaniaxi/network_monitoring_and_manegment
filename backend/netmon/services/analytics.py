"""Historical analysis: time-bucketed series, dashboard KPIs and reports.

Aggregation happens in SQL (``GROUP BY`` over an epoch bucket) so the amount of data moved
into Python is bounded by ``buckets x devices`` regardless of how many raw samples exist.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from netmon.db.base import utcnow
from netmon.models import (
    Alert,
    AlertMetric,
    AlertSeverity,
    AlertStatus,
    Device,
    DeviceStatus,
    Interface,
    MetricSample,
)

TimeRange = Literal["1h", "6h", "24h", "7d", "30d"]

RANGE_PRESETS: dict[str, tuple[timedelta, int]] = {
    "1h": (timedelta(hours=1), 60),
    "6h": (timedelta(hours=6), 300),
    "24h": (timedelta(hours=24), 900),
    "7d": (timedelta(days=7), 3600),
    "30d": (timedelta(days=30), 4 * 3600),
}


@dataclass(frozen=True, slots=True)
class Window:
    start: datetime
    end: datetime
    bucket_seconds: int

    @classmethod
    def from_range(cls, time_range: str, now: datetime | None = None) -> Window:
        span, bucket = RANGE_PRESETS[time_range]
        end = now or utcnow()
        return cls(start=end - span, end=end, bucket_seconds=bucket)

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def bucket_starts(self) -> list[int]:
        b = self.bucket_seconds
        first = int(self.start.timestamp()) // b * b
        last = int(self.end.timestamp()) // b * b
        return list(range(first, last + 1, b))


def bucket_expr(dialect: str, column: Any, seconds: int) -> ColumnElement[Any]:
    """Portable ``floor(epoch(column) / seconds) * seconds``."""
    if dialect == "postgresql":
        return func.floor(sa.extract("epoch", column) / seconds) * seconds
    return sa.cast(func.strftime("%s", column), sa.Integer) // seconds * seconds


def _f(value: Any, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def _dialect(session: AsyncSession) -> str:
    return session.bind.dialect.name if session.bind is not None else "sqlite"


_AVAILABILITY = func.avg(case((MetricSample.is_up.is_(True), 100.0), else_=0.0))


# ---------------------------------------------------------------------------- series
async def device_series(
    session: AsyncSession, device_id: int, window: Window
) -> list[dict[str, Any]]:
    bucket = bucket_expr(_dialect(session), MetricSample.ts, window.bucket_seconds).label("b")
    stmt = (
        select(
            bucket,
            func.avg(MetricSample.latency_ms),
            func.max(MetricSample.latency_max_ms),
            func.avg(MetricSample.jitter_ms),
            func.avg(MetricSample.packet_loss),
            _AVAILABILITY,
            func.avg(MetricSample.cpu_percent),
            func.avg(MetricSample.memory_percent),
            func.avg(MetricSample.in_bps),
            func.avg(MetricSample.out_bps),
            func.max(MetricSample.bandwidth_util),
            func.count(),
        )
        .where(MetricSample.device_id == device_id, MetricSample.ts >= window.start)
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = {int(r[0]): r for r in (await session.execute(stmt)).all()}
    points: list[dict[str, Any]] = []
    for start in window.bucket_starts():
        r = rows.get(start)
        points.append(
            {
                "ts": datetime.fromtimestamp(start, UTC),
                "latency_ms": _f(r[1]) if r else None,
                "latency_max_ms": _f(r[2]) if r else None,
                "jitter_ms": _f(r[3]) if r else None,
                "packet_loss": _f(r[4], 2) if r else None,
                "availability": _f(r[5], 2) if r else None,
                "cpu_percent": _f(r[6], 2) if r else None,
                "memory_percent": _f(r[7], 2) if r else None,
                "in_bps": _f(r[8], 0) if r else None,
                "out_bps": _f(r[9], 0) if r else None,
                "bandwidth_util": _f(r[10], 2) if r else None,
                "samples": int(r[11]) if r else 0,
            }
        )
    return points


async def _per_device_buckets(
    session: AsyncSession, window: Window, bucket_seconds: int | None = None
) -> Sequence[Any]:
    bucket = bucket_expr(
        _dialect(session), MetricSample.ts, bucket_seconds or window.bucket_seconds
    ).label("b")
    stmt = (
        select(
            bucket,
            MetricSample.device_id,
            func.avg(MetricSample.latency_ms),
            func.avg(MetricSample.packet_loss),
            _AVAILABILITY,
            func.avg(MetricSample.in_bps),
            func.avg(MetricSample.out_bps),
        )
        .where(MetricSample.ts >= window.start)
        .group_by(bucket, MetricSample.device_id)
    )
    return (await session.execute(stmt)).all()


async def network_series(session: AsyncSession, window: Window) -> list[dict[str, Any]]:
    """Network-wide series: mean latency/loss/availability, total throughput."""
    grouped: dict[int, list[Any]] = defaultdict(list)
    for row in await _per_device_buckets(session, window):
        grouped[int(row[0])].append(row)

    def mean(values: list[Any]) -> float | None:
        vals = [float(v) for v in values if v is not None]
        return statistics.fmean(vals) if vals else None

    points = []
    for start in window.bucket_starts():
        rows = grouped.get(start, [])
        has_traffic = any(r[5] is not None or r[6] is not None for r in rows)
        points.append(
            {
                "ts": datetime.fromtimestamp(start, UTC),
                "latency_ms": _f(mean([r[2] for r in rows])),
                "packet_loss": _f(mean([r[3] for r in rows]), 2),
                "availability": _f(mean([r[4] for r in rows]), 2),
                "in_bps": _f(sum(float(r[5] or 0) for r in rows), 0) if has_traffic else None,
                "out_bps": _f(sum(float(r[6] or 0) for r in rows), 0) if has_traffic else None,
                "devices": len(rows),
            }
        )
    return points


# ---------------------------------------------------------------------------- dashboard
async def dashboard_summary(session: AsyncSession) -> dict[str, Any]:
    devices = (await session.scalars(select(Device))).all()
    counts = {s.value: 0 for s in DeviceStatus}
    by_type: dict[str, int] = defaultdict(int)
    unmonitored = 0
    throughput = 0.0
    utils: list[float] = []
    for d in devices:
        by_type[d.device_type.value] += 1
        if not d.is_monitored:
            unmonitored += 1
            continue
        counts[d.status.value] += 1
        throughput += (d.last_in_bps or 0) + (d.last_out_bps or 0)
        if d.last_bandwidth_util is not None:
            utils.append(d.last_bandwidth_util)

    now = utcnow()
    day = await session.execute(
        select(_AVAILABILITY, func.count()).where(MetricSample.ts >= now - timedelta(hours=24))
    )
    availability_24h, samples_24h = day.one()
    hour = await session.execute(
        select(func.avg(MetricSample.latency_ms), func.avg(MetricSample.packet_loss)).where(
            MetricSample.ts >= now - timedelta(hours=1)
        )
    )
    latency_1h, loss_1h = hour.one()

    alert_rows = await session.execute(
        select(Alert.status, Alert.severity, func.count())
        .where(Alert.status != AlertStatus.RESOLVED)
        .group_by(Alert.status, Alert.severity)
    )
    alerts = {"active": 0, "acknowledged": 0, **{s.value: 0 for s in AlertSeverity}}
    for status, severity, n in alert_rows.all():
        alerts[status.value] += n
        alerts[severity.value] += n

    return {
        "devices": {"total": len(devices), "unmonitored": unmonitored, **counts},
        "by_type": dict(by_type),
        "availability_24h": _f(availability_24h, 2),
        "samples_24h": int(samples_24h or 0),
        "avg_latency_ms_1h": _f(latency_1h),
        "avg_packet_loss_1h": _f(loss_1h, 2),
        "throughput_bps": round(throughput, 0),
        "avg_bandwidth_util": _f(statistics.fmean(utils), 2) if utils else None,
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------- reports
def _overlap_seconds(start: datetime, end: datetime | None, window: Window) -> float:
    s = max(start, window.start)
    e = min(end or window.end, window.end)
    return max(0.0, (e - s).total_seconds())


async def availability_report(session: AsyncSession, window: Window) -> list[dict[str, Any]]:
    stats_rows = await session.execute(
        select(
            MetricSample.device_id,
            func.count(),
            _AVAILABILITY,
            func.avg(MetricSample.latency_ms),
            func.max(MetricSample.latency_max_ms),
            func.avg(MetricSample.packet_loss),
            func.avg(MetricSample.jitter_ms),
        )
        .where(MetricSample.ts >= window.start)
        .group_by(MetricSample.device_id)
    )
    stats = {r[0]: r for r in stats_rows.all()}

    outages = (
        await session.scalars(
            select(Alert).where(
                Alert.metric == AlertMetric.DEVICE_DOWN,
                sa.or_(Alert.resolved_at.is_(None), Alert.resolved_at >= window.start),
                Alert.triggered_at <= window.end,
            )
        )
    ).all()
    incidents: dict[int, list[Alert]] = defaultdict(list)
    for alert in outages:
        incidents[alert.device_id].append(alert)

    report = []
    for device in (await session.scalars(select(Device).order_by(Device.name))).all():
        r = stats.get(device.id)
        device_outages = incidents.get(device.id, [])
        downtime = sum(
            _overlap_seconds(a.first_breach_at or a.triggered_at, a.resolved_at, window)
            for a in device_outages
        )
        repairs = [
            (a.resolved_at - (a.first_breach_at or a.triggered_at)).total_seconds()
            for a in device_outages
            if a.resolved_at is not None
        ]
        report.append(
            {
                "device_id": device.id,
                "name": device.name,
                "ip_address": device.ip_address,
                "device_type": device.device_type.value,
                "status": device.status.value,
                "samples": int(r[1]) if r else 0,
                "availability": _f(r[2], 3) if r else None,
                "avg_latency_ms": _f(r[3]) if r else None,
                "max_latency_ms": _f(r[4]) if r else None,
                "avg_packet_loss": _f(r[5], 2) if r else None,
                "avg_jitter_ms": _f(r[6]) if r else None,
                "incidents": len(device_outages),
                "downtime_seconds": round(downtime),
                "mttr_seconds": round(statistics.fmean(repairs)) if repairs else None,
            }
        )
    return report


async def top_failing(
    session: AsyncSession, window: Window, limit: int = 10
) -> list[dict[str, Any]]:
    rows = await availability_report(session, window)
    failing = [r for r in rows if r["incidents"] or (r["availability"] or 100) < 100]
    failing.sort(key=lambda r: (-r["incidents"], -r["downtime_seconds"], r["availability"] or 0))
    return failing[:limit]


async def traffic_heatmap(
    session: AsyncSession, window: Window, tz_offset_minutes: int = 0
) -> dict[str, Any]:
    """Average total throughput by weekday x hour - reveals high-traffic periods."""
    per_bucket: dict[int, float] = defaultdict(float)
    seen: set[int] = set()
    for row in await _per_device_buckets(session, window, bucket_seconds=3600):
        if row[5] is None and row[6] is None:
            continue
        seen.add(int(row[0]))
        per_bucket[int(row[0])] += float(row[5] or 0) + float(row[6] or 0)

    cells: dict[tuple[int, int], list[float]] = defaultdict(list)
    offset = timedelta(minutes=tz_offset_minutes)
    for epoch in seen:
        local = datetime.fromtimestamp(epoch, UTC) + offset
        cells[(local.weekday(), local.hour)].append(per_bucket[epoch])
    matrix = [
        [_f(statistics.fmean(cells[(d, h)]), 0) if cells.get((d, h)) else None for h in range(24)]
        for d in range(7)
    ]
    flat = [(v, d, h) for d, row in enumerate(matrix) for h, v in enumerate(row) if v is not None]
    peak = max(flat, default=None)
    return {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "matrix_bps": matrix,
        "peak": {"day": peak[1], "hour": peak[2], "bps": peak[0]} if peak else None,
    }


async def bottlenecks(session: AsyncSession, window: Window, limit: int = 10) -> dict[str, Any]:
    rows = await session.execute(
        select(
            MetricSample.device_id,
            func.avg(MetricSample.bandwidth_util),
            func.max(MetricSample.bandwidth_util),
            func.avg(MetricSample.cpu_percent),
            func.max(MetricSample.cpu_percent),
            func.avg(MetricSample.latency_ms),
            func.avg(MetricSample.packet_loss),
        )
        .where(MetricSample.ts >= window.start)
        .group_by(MetricSample.device_id)
    )
    names = {d.id: d for d in (await session.scalars(select(Device))).all()}
    devices: list[dict[str, Any]] = []
    for r in rows.all():
        device = names.get(r[0])
        if device is None:
            continue
        devices.append(
            {
                "device_id": device.id,
                "name": device.name,
                "device_type": device.device_type.value,
                "avg_bandwidth_util": _f(r[1], 2),
                "max_bandwidth_util": _f(r[2], 2),
                "avg_cpu_percent": _f(r[3], 2),
                "max_cpu_percent": _f(r[4], 2),
                "avg_latency_ms": _f(r[5]),
                "avg_packet_loss": _f(r[6], 2),
            }
        )

    def score(d: dict[str, Any]) -> float:
        return max(d["avg_bandwidth_util"] or 0, (d["avg_cpu_percent"] or 0) * 0.8) + (
            d["avg_packet_loss"] or 0
        )

    devices.sort(key=score, reverse=True)
    ifaces = (
        await session.scalars(
            select(Interface)
            .where(Interface.utilization_percent.is_not(None))
            .order_by(Interface.utilization_percent.desc())
            .limit(limit)
        )
    ).all()
    return {
        "devices": devices[:limit],
        "interfaces": [
            {
                "device_id": i.device_id,
                "device": names[i.device_id].name if i.device_id in names else None,
                "interface": i.name,
                "speed_mbps": i.speed_mbps,
                "in_bps": i.in_bps,
                "out_bps": i.out_bps,
                "utilization_percent": i.utilization_percent,
            }
            for i in ifaces
        ],
    }


async def degradation(session: AsyncSession, window: Window) -> list[dict[str, Any]]:
    """Compare first vs second half of the window to spot devices getting worse."""
    midpoint = window.start + (window.end - window.start) / 2
    half = case((MetricSample.ts >= midpoint, 1), else_=0).label("half")
    rows = await session.execute(
        select(
            MetricSample.device_id,
            half,
            func.avg(MetricSample.latency_ms),
            func.avg(MetricSample.packet_loss),
            _AVAILABILITY,
        )
        .where(MetricSample.ts >= window.start)
        .group_by(MetricSample.device_id, half)
    )
    halves: dict[int, dict[int, Any]] = defaultdict(dict)
    for r in rows.all():
        halves[r[0]][int(r[1])] = r
    names = {d.id: d.name for d in (await session.scalars(select(Device))).all()}

    def pct_change(before: Any, after: Any) -> float | None:
        if before is None or after is None or float(before) == 0:
            return None
        return round(100.0 * (float(after) - float(before)) / float(before), 1)

    result: list[dict[str, Any]] = []
    for device_id, parts in halves.items():
        if 0 not in parts or 1 not in parts or device_id not in names:
            continue
        a, b = parts[0], parts[1]
        latency_change = pct_change(a[2], b[2])
        loss_delta = _f((b[3] or 0) - (a[3] or 0), 2)
        availability_delta = _f((b[4] or 0) - (a[4] or 0), 2)
        degraded = bool(
            (latency_change is not None and latency_change > 50 and (b[2] or 0) - (a[2] or 0) > 5)
            or (loss_delta or 0) > 2
            or (availability_delta or 0) < -1
        )
        result.append(
            {
                "device_id": device_id,
                "name": names[device_id],
                "latency_before_ms": _f(a[2]),
                "latency_after_ms": _f(b[2]),
                "latency_change_percent": latency_change,
                "packet_loss_before": _f(a[3], 2),
                "packet_loss_after": _f(b[3], 2),
                "availability_before": _f(a[4], 2),
                "availability_after": _f(b[4], 2),
                "degraded": degraded,
            }
        )
    result.sort(key=lambda r: (not r["degraded"], -(r["latency_change_percent"] or 0)))
    return result


SAMPLE_COLUMNS = [
    "ts", "device_id", "device", "is_up", "latency_ms", "latency_min_ms", "latency_max_ms",
    "jitter_ms", "packet_loss", "cpu_percent", "memory_percent", "in_bps", "out_bps",
    "bandwidth_util", "poll_duration_ms",
]  # fmt: skip


async def iter_samples(
    session: AsyncSession, window: Window, device_id: int | None = None
) -> AsyncIterator[list[Any]]:
    """Stream raw samples (for CSV export / offline research analysis)."""
    stmt = (
        select(MetricSample, Device.name)
        .join(Device, Device.id == MetricSample.device_id)
        .where(MetricSample.ts >= window.start)
        .order_by(MetricSample.ts)
        .execution_options(yield_per=2000)
    )
    if device_id is not None:
        stmt = stmt.where(MetricSample.device_id == device_id)
    result = await session.stream(stmt)
    async for sample, name in result:
        yield [
            sample.ts.isoformat(), sample.device_id, name, int(sample.is_up), sample.latency_ms,
            sample.latency_min_ms, sample.latency_max_ms, sample.jitter_ms, sample.packet_loss,
            sample.cpu_percent, sample.memory_percent, sample.in_bps, sample.out_bps,
            sample.bandwidth_util, sample.poll_duration_ms,
        ]  # fmt: skip


async def detection_report(session: AsyncSession, window: Window) -> dict[str, Any]:
    """Research metric: how quickly outages are detected and resolved.

    detection delay = ``triggered_at - first_breach_at`` (latency added by debouncing) and the
    time to recovery for resolved outages.
    """
    alerts = (
        await session.scalars(
            select(Alert).where(
                Alert.metric == AlertMetric.DEVICE_DOWN, Alert.triggered_at >= window.start
            )
        )
    ).all()
    delays = [
        (a.triggered_at - a.first_breach_at).total_seconds() for a in alerts if a.first_breach_at
    ]
    recoveries = [
        (a.resolved_at - (a.first_breach_at or a.triggered_at)).total_seconds()
        for a in alerts
        if a.resolved_at
    ]

    def describe(values: list[float]) -> dict[str, float | int | None]:
        if not values:
            return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
        return {
            "count": len(values),
            "mean": round(statistics.fmean(values), 2),
            "median": round(statistics.median(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }

    return {
        "outages": len(alerts),
        "detection_delay_seconds": describe(delays),
        "time_to_recovery_seconds": describe(recoveries),
    }
