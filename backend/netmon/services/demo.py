"""Synthetic history for demos: back-fills metric samples and matching outage alerts.

Uses the same device "personalities" as the live simulation backend (latency ranges, diurnal
traffic, flaky database server) so historical charts, reports and the research metrics have
realistic data immediately after ``netmon seed-demo --history-hours N``.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from netmon.db.base import utcnow
from netmon.models import (
    Alert,
    AlertMetric,
    AlertSeverity,
    AlertStatus,
    Device,
    MetricSample,
)
from netmon.services.monitoring.simulation import (
    CPU_BASE,
    INTERFACES,
    LATENCY_RANGE,
    diurnal_factor,
    stable_seed,
)

BATCH = 5000


async def backfill_history(
    session: AsyncSession, hours: int, step_seconds: int = 300, seed: int = 7
) -> int:
    """Insert ``hours`` of history for every device. Returns the number of samples."""
    devices = (await session.scalars(select(Device).order_by(Device.id))).all()
    end = utcnow().replace(second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    steps = int((end - start).total_seconds() // step_seconds)
    rows: list[dict[str, object]] = []
    alerts: list[Alert] = []
    total = 0

    for device in devices:
        rng = random.Random(stable_seed(seed, device.id, device.name))
        lo, hi = LATENCY_RANGE.get(device.device_type, (1.0, 10.0))
        base_latency = rng.uniform(lo, hi)
        lowered = device.name.lower()
        flaky = "database" in lowered or lowered.startswith("db")
        cpu_base = CPU_BASE.get(device.device_type, 15)
        memory = rng.uniform(35, 70)
        ifaces = INTERFACES.get(device.device_type, [])
        # Latency creeps up over the last third of the window on one device so the
        # degradation report has something to find.
        degrading = device.device_type.value == "access_point"
        outage_left = 0
        outage_start: datetime | None = None

        for i in range(steps):
            ts = start + timedelta(seconds=i * step_seconds)
            load = diurnal_factor(ts.astimezone())
            if outage_left == 0 and rng.random() < (0.012 if flaky else 0.0006):
                outage_left = rng.randint(1, 4)
                outage_start = ts
            is_up = outage_left == 0
            if not is_up:
                outage_left -= 1
                if outage_left == 0 and outage_start is not None:
                    recovered = ts + timedelta(seconds=step_seconds)
                    alerts.append(
                        Alert(
                            device_id=device.id,
                            metric=AlertMetric.DEVICE_DOWN,
                            severity=AlertSeverity.CRITICAL,
                            status=AlertStatus.RESOLVED,
                            title="Device unreachable",
                            message=f"ALERT: {device.name} is unreachable.",
                            value=1.0,
                            threshold=1.0,
                            first_breach_at=outage_start,
                            triggered_at=outage_start + timedelta(seconds=step_seconds),
                            resolved_at=recovered,
                            resolution_note=f"RESOLVED: {device.name} is reachable again.",
                        )
                    )
            drift = 1.0 + (4.0 * max(0.0, (i / steps - 0.66) / 0.34) if degrading else 0.0)
            rtts = [
                base_latency * drift * (1 + 0.6 * load) * rng.lognormvariate(0, 0.25)
                for _ in range(3)
            ]
            loss = 0.0 if rng.random() > 0.01 else rng.choice([33.33, 66.67])
            row: dict[str, object] = {
                "device_id": device.id,
                "ts": ts,
                "is_up": is_up,
                "latency_ms": round(sum(rtts) / 3, 3) if is_up else None,
                "latency_min_ms": round(min(rtts), 3) if is_up else None,
                "latency_max_ms": round(max(rtts), 3) if is_up else None,
                "jitter_ms": round(abs(rtts[0] - rtts[1]), 3) if is_up else None,
                "packet_loss": loss if is_up else 100.0,
                "poll_duration_ms": round(rng.uniform(1, 40), 2),
            }
            if device.snmp_enabled and is_up:
                in_bps = out_bps = 0.0
                busiest = 0.0
                for _name, speed, peak in ifaces:
                    util = min(0.97, peak * load * rng.lognormvariate(0, 0.2))
                    in_bps += speed * 1e6 * util
                    out_bps += speed * 1e6 * util * rng.uniform(0.15, 0.6)
                    busiest = max(busiest, util * 100)
                memory = min(88.0, max(20.0, memory + rng.gauss(0, 0.4)))
                cpu = cpu_base * (0.6 + 0.8 * load) + rng.gauss(0, 3)
                row.update(
                    cpu_percent=round(min(99.0, max(0.5, cpu)), 2),
                    memory_percent=round(memory, 2),
                    in_bps=round(in_bps, 2) if ifaces else None,
                    out_bps=round(out_bps, 2) if ifaces else None,
                    bandwidth_util=round(busiest, 2) if ifaces else None,
                )
            rows.append(row)
            if len(rows) >= BATCH:
                await session.execute(insert(MetricSample), rows)
                total += len(rows)
                rows.clear()

    if rows:
        await session.execute(insert(MetricSample), rows)
        total += len(rows)
    session.add_all(alerts)
    await session.commit()
    return total
