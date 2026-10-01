"""The monitoring engine: schedules device polls and turns raw measurements into state.

Pipeline for one device poll::

    probe (ICMP/TCP) ─► SNMP (if enabled and reachable) ─► rate calculation
        ─► persist MetricSample + device/interface state ─► alert evaluation
        ─► commit ─► live events (WebSocket) + notifications (webhook / e-mail)

Scheduling is a 1-second tick that dispatches every device whose next due time has passed,
with a global concurrency limit. First polls of newly added devices are spread over a few
seconds to avoid a thundering herd after start-up.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import random
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from netmon.core.config import Settings
from netmon.db.base import utcnow
from netmon.models import (
    Alert,
    AlertStatus,
    CheckMethod,
    Device,
    DeviceStatus,
    Interface,
    MetricSample,
)
from netmon.services.alerting.engine import AlertEngine, AlertTransition
from netmon.services.alerting.notifiers import Notifier
from netmon.services.events import EventHub
from netmon.services.monitoring.backends import MonitorBackend, create_backend
from netmon.services.monitoring.rates import octets_to_bps, utilization
from netmon.services.monitoring.types import DeviceTarget, ProbeResult, SnmpSnapshot
from netmon.services.telemetry import PollerStats, ProcessSampler, PrometheusMetrics

log = logging.getLogger(__name__)

TARGET_REFRESH_SECONDS = 5.0
RETENTION_EVERY_SECONDS = 3600.0


class MonitoringService:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        hub: EventHub,
        backend: MonitorBackend | None = None,
        notifier: Notifier | None = None,
        prometheus: PrometheusMetrics | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.hub = hub
        self.backend: MonitorBackend = backend or create_backend(settings)
        self.alerts = AlertEngine()
        self.notifier = notifier or Notifier(settings)
        self.prometheus = prometheus or PrometheusMetrics()
        self.stats = PollerStats()
        self.process = ProcessSampler()

        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_polls)
        self._targets: list[DeviceTarget] = []
        self._targets_loaded_at = 0.0
        self._next_due: dict[int, float] = {}
        self._in_flight: dict[int, asyncio.Task[Device | None]] = {}
        self._last_retention = 0.0

    # ------------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)

    async def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self.stats = PollerStats()
        self._task = asyncio.create_task(self._run(), name="netmon-scheduler")
        log.info(
            "monitoring engine started (backend=%s, interval=%ss, concurrency=%s)",
            self.backend.name, self.settings.poll_interval_seconds,
            self.settings.max_concurrent_polls,
        )  # fmt: skip

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await asyncio.wait({self._task}, timeout=5)
            self._task.cancel()
        for task in list(self._in_flight.values()):
            task.cancel()
        if self._in_flight:
            await asyncio.gather(*self._in_flight.values(), return_exceptions=True)
        await self.notifier.aclose()
        await self.backend.close()
        log.info("monitoring engine stopped")

    def invalidate(self) -> None:
        """Force a reload of the device list (called after device CRUD)."""
        self._targets_loaded_at = 0.0

    # ------------------------------------------------------------------ scheduler
    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._tick()
            except Exception:
                log.exception("scheduler tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=1.0)

    async def _load_targets(self) -> list[DeviceTarget]:
        now = time.monotonic()
        if now - self._targets_loaded_at >= TARGET_REFRESH_SECONDS:
            async with self.session_factory() as session:
                devices = (
                    await session.scalars(select(Device).where(Device.is_monitored.is_(True)))
                ).all()
                self._targets = [
                    DeviceTarget.from_device(d, self.settings.poll_interval_seconds)
                    for d in devices
                ]
            self._targets_loaded_at = now
        return self._targets

    async def _tick(self) -> None:
        now = time.monotonic()
        targets = await self._load_targets()
        active: set[int] = set()
        for target in targets:
            active.add(target.id)
            if target.id in self._in_flight:
                continue
            due = self._next_due.get(target.id)
            if due is None:
                due = now + random.uniform(0, min(5.0, target.poll_interval))
                self._next_due[target.id] = due
            if due <= now:
                self._next_due[target.id] = now + target.poll_interval
                self._spawn(target)
        for stale in set(self._next_due) - active:
            del self._next_due[stale]
            self.alerts.reset_device(stale)
        if now - self._last_retention >= RETENTION_EVERY_SECONDS:
            self._last_retention = now
            await self.apply_retention()

    def _spawn(self, target: DeviceTarget) -> asyncio.Task[Device | None]:
        task = asyncio.create_task(self._guarded_poll(target), name=f"poll-{target.id}")
        self._in_flight[target.id] = task
        task.add_done_callback(functools.partial(self._poll_done, target.id))
        return task

    def _poll_done(self, device_id: int, _task: asyncio.Task[Device | None]) -> None:
        self._in_flight.pop(device_id, None)

    async def _guarded_poll(self, target: DeviceTarget) -> Device | None:
        async with self._semaphore:
            try:
                return await self.poll(target)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.stats.poll_errors += 1
                log.exception("poll of %s (%s) failed", target.name, target.host)
                return None

    async def poll_device_now(self, device_id: int) -> Device | None:
        """Poll a device immediately (the "Check now" button)."""
        if (task := self._in_flight.get(device_id)) is not None:
            return await task
        async with self.session_factory() as session:
            device = await session.get(Device, device_id)
            if device is None:
                return None
            target = DeviceTarget.from_device(device, self.settings.poll_interval_seconds)
        self._next_due[device_id] = time.monotonic() + target.poll_interval
        return await self._spawn(target)

    # ------------------------------------------------------------------ one poll
    async def poll(self, target: DeviceTarget) -> Device | None:
        started = time.perf_counter()
        probe = await self.backend.probe(target)
        snapshot: SnmpSnapshot | None = None
        snmp_error: str | None = None
        if probe.is_up and target.snmp is not None:
            try:
                snapshot = await self.backend.snmp_poll(target)
            except Exception as exc:  # SNMP agent down/misconfigured must not fail the poll
                snmp_error = f"SNMP: {exc}"[:500]
        duration_ms = (time.perf_counter() - started) * 1000

        async with self.session_factory() as session:
            device = await session.get(Device, target.id)
            if device is None:
                return None
            now = utcnow()
            previous_status = device.status
            sample = MetricSample(
                device_id=device.id,
                ts=now,
                is_up=probe.is_up,
                latency_ms=probe.latency_ms,
                latency_min_ms=probe.min_ms,
                latency_max_ms=probe.max_ms,
                jitter_ms=probe.jitter_ms,
                packet_loss=probe.packet_loss,
                poll_duration_ms=round(duration_ms, 2),
            )
            self._apply_probe(device, probe, now)
            if snapshot is not None:
                await self._apply_snmp(session, device, snapshot, sample, now)
            device.last_error = probe.error or snmp_error
            session.add(sample)
            await session.flush()
            transitions = await self.alerts.evaluate(session, device, sample)
            await session.commit()

        self._record(target, device, probe, snapshot, duration_ms, transitions)
        self._publish(device, sample, previous_status, transitions)
        self.notifier.dispatch(transitions)
        return device

    def _apply_probe(self, device: Device, probe: ProbeResult, now: datetime) -> None:
        s = self.settings
        device.last_checked_at = now
        if probe.is_up:
            device.consecutive_failures = 0
            device.last_seen_at = now
            device.last_latency_ms = probe.latency_ms
            device.last_packet_loss = probe.packet_loss
            degraded = probe.packet_loss >= s.degraded_packet_loss or (
                probe.latency_ms is not None and probe.latency_ms >= s.degraded_latency_ms
            )
            new_status = DeviceStatus.DEGRADED if degraded else DeviceStatus.UP
        else:
            device.consecutive_failures += 1
            device.last_latency_ms = None
            device.last_packet_loss = 100.0
            new_status = (
                DeviceStatus.DOWN
                if device.consecutive_failures >= s.down_after_failures
                else device.status
            )
        if new_status != device.status:
            device.status = new_status
            device.status_changed_at = now

    async def _apply_snmp(
        self,
        session: AsyncSession,
        device: Device,
        snap: SnmpSnapshot,
        sample: MetricSample,
        now: datetime,
    ) -> None:
        device.sys_name = snap.sys_name or device.sys_name
        device.sys_descr = snap.sys_descr or device.sys_descr
        device.sys_object_id = snap.sys_object_id or device.sys_object_id
        device.uptime_seconds = snap.uptime_seconds
        device.last_cpu_percent = sample.cpu_percent = snap.cpu_percent
        device.last_memory_percent = sample.memory_percent = snap.memory_percent

        existing = {
            i.if_index: i
            for i in (
                await session.scalars(select(Interface).where(Interface.device_id == device.id))
            ).all()
        }
        total_in = total_out = 0.0
        have_rate = False
        busiest: float | None = None
        for counters in snap.interfaces:
            iface = existing.pop(counters.if_index, None)
            if iface is None:
                iface = Interface(device_id=device.id, if_index=counters.if_index)
                session.add(iface)
            elapsed = (now - iface.counters_at).total_seconds() if iface.counters_at else 0.0
            same_width = iface.counters_64bit == counters.counters_64bit
            in_bps = out_bps = None
            if same_width:
                in_bps = octets_to_bps(iface.in_octets, counters.in_octets, elapsed,
                                       counters.counters_64bit, counters.speed_mbps)  # fmt: skip
                out_bps = octets_to_bps(iface.out_octets, counters.out_octets, elapsed,
                                        counters.counters_64bit, counters.speed_mbps)  # fmt: skip
            util = utilization(in_bps, out_bps, counters.speed_mbps)

            iface.name = counters.name[:255]
            iface.alias = counters.alias[:255] if counters.alias else None
            iface.if_type = counters.if_type
            iface.admin_status = counters.admin_status
            iface.oper_status = counters.oper_status
            iface.speed_mbps = counters.speed_mbps
            iface.in_octets = counters.in_octets
            iface.out_octets = counters.out_octets
            iface.counters_64bit = counters.counters_64bit
            iface.counters_at = now
            iface.in_bps = round(in_bps, 2) if in_bps is not None else None
            iface.out_bps = round(out_bps, 2) if out_bps is not None else None
            iface.utilization_percent = util
            iface.updated_at = now

            if counters.is_loopback or counters.oper_status != "up":
                continue
            if in_bps is not None or out_bps is not None:
                have_rate = True
                total_in += in_bps or 0.0
                total_out += out_bps or 0.0
            if util is not None:
                busiest = util if busiest is None else max(busiest, util)
        for gone in existing.values():
            await session.delete(gone)

        sample.in_bps = round(total_in, 2) if have_rate else None
        sample.out_bps = round(total_out, 2) if have_rate else None
        sample.bandwidth_util = busiest
        device.last_in_bps = sample.in_bps
        device.last_out_bps = sample.out_bps
        device.last_bandwidth_util = busiest

    # ------------------------------------------------------------------ side effects
    def _record(
        self,
        target: DeviceTarget,
        device: Device,
        probe: ProbeResult,
        snapshot: SnmpSnapshot | None,
        duration_ms: float,
        transitions: list[AlertTransition],
    ) -> None:
        self.stats.record(
            duration_ms=duration_ms,
            is_up=probe.is_up,
            packets=probe.packets_sent,
            snmp_requests=snapshot.requests if snapshot else 0,
            tcp=target.check_method == CheckMethod.TCP,
        )
        p = self.prometheus
        labels = (device.name, device.device_type.value)
        p.polls.labels("up" if probe.is_up else "down").inc()
        p.poll_duration.observe(duration_ms / 1000)
        p.device_up.labels(*labels).set(1 if probe.is_up else 0)
        p.packet_loss.labels(*labels).set(probe.packet_loss)
        if probe.latency_ms is not None:
            p.latency.labels(*labels).set(probe.latency_ms)
        if device.last_cpu_percent is not None:
            p.cpu.labels(*labels).set(device.last_cpu_percent)
        if device.last_memory_percent is not None:
            p.memory.labels(*labels).set(device.last_memory_percent)
        if device.last_in_bps is not None or device.last_out_bps is not None:
            p.throughput.labels(*labels).set((device.last_in_bps or 0) + (device.last_out_bps or 0))
        for t in transitions:
            if t.kind == "opened":
                p.alerts_opened.labels(t.alert.severity.value).inc()

    def _publish(
        self,
        device: Device,
        sample: MetricSample,
        previous_status: DeviceStatus,
        transitions: list[AlertTransition],
    ) -> None:
        self.hub.publish(
            "device.sample",
            {
                "device_id": device.id,
                "name": device.name,
                "status": device.status.value,
                "ts": sample.ts.isoformat(),
                "is_up": sample.is_up,
                "latency_ms": sample.latency_ms,
                "packet_loss": sample.packet_loss,
                "cpu_percent": sample.cpu_percent,
                "memory_percent": sample.memory_percent,
                "in_bps": sample.in_bps,
                "out_bps": sample.out_bps,
                "bandwidth_util": sample.bandwidth_util,
            },
        )
        if device.status != previous_status:
            self.hub.publish(
                "device.status",
                {
                    "device_id": device.id,
                    "name": device.name,
                    "status": device.status.value,
                    "previous": previous_status.value,
                },
            )
        for t in transitions:
            self.hub.publish(
                f"alert.{t.kind}",
                {
                    "id": t.alert.id,
                    "device_id": t.alert.device_id,
                    "device": t.device_name,
                    "severity": t.alert.severity.value,
                    "title": t.alert.title,
                    "message": t.alert.message
                    if t.kind == "opened"
                    else (t.alert.resolution_note or t.alert.message),
                },
            )

    # ------------------------------------------------------------------ housekeeping
    async def apply_retention(self) -> int:
        cutoff = utcnow() - timedelta(days=self.settings.metrics_retention_days)
        async with self.session_factory() as session:
            result = await session.execute(delete(MetricSample).where(MetricSample.ts < cutoff))
            await session.execute(
                delete(Alert).where(
                    Alert.status == AlertStatus.RESOLVED, Alert.resolved_at < cutoff
                )
            )
            await session.commit()
        removed = int(getattr(result, "rowcount", 0) or 0)
        if removed:
            log.info("retention: removed %d samples older than %s", removed, cutoff.date())
        return removed
