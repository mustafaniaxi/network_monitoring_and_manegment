"""Self-monitoring: Prometheus metrics and monitoring-overhead accounting.

The overhead figures (packets, estimated bytes, poll duration, process CPU/RAM) feed the
research component - "how much load does monitoring itself put on the network and server?".
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psutil
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Wire-size estimates used for overhead accounting (IPv4):
#   ICMP echo = 20 B IP + 8 B ICMP + 56 B payload = 84 B each way.
#   SNMP GET/GETBULK request+response averages ~600 B on small agents.
ICMP_BYTES_PER_PROBE = 84 * 2
TCP_BYTES_PER_PROBE = 60 * 3 + 52 * 2  # SYN/SYN-ACK/ACK + FIN/ACK
SNMP_BYTES_PER_REQUEST = 600


@dataclass
class PollerStats:
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    polls_total: int = 0
    polls_down: int = 0
    poll_errors: int = 0
    probe_packets: int = 0
    snmp_requests: int = 0
    est_bytes: int = 0
    last_poll_at: datetime | None = None
    avg_poll_ms: float = 0.0
    max_poll_ms: float = 0.0
    _ema_alpha: float = 0.1

    def record(self, *, duration_ms: float, is_up: bool, packets: int, snmp_requests: int,
               tcp: bool) -> None:  # fmt: skip
        self.polls_total += 1
        self.polls_down += 0 if is_up else 1
        self.probe_packets += packets
        self.snmp_requests += snmp_requests
        per_probe = TCP_BYTES_PER_PROBE if tcp else ICMP_BYTES_PER_PROBE
        self.est_bytes += packets * per_probe + snmp_requests * SNMP_BYTES_PER_REQUEST
        self.last_poll_at = datetime.now(UTC)
        self.avg_poll_ms = (
            duration_ms
            if self.polls_total == 1
            else self._ema_alpha * duration_ms + (1 - self._ema_alpha) * self.avg_poll_ms
        )
        self.max_poll_ms = max(self.max_poll_ms, duration_ms)

    def as_dict(self) -> dict[str, Any]:
        uptime = max(1.0, (datetime.now(UTC) - self.started_at).total_seconds())
        return {
            "started_at": self.started_at,
            "uptime_seconds": round(uptime),
            "polls_total": self.polls_total,
            "polls_down": self.polls_down,
            "poll_errors": self.poll_errors,
            "probe_packets": self.probe_packets,
            "snmp_requests": self.snmp_requests,
            "estimated_bytes": self.est_bytes,
            "estimated_bandwidth_bps": round(self.est_bytes * 8 / uptime, 2),
            "polls_per_minute": round(self.polls_total * 60 / uptime, 2),
            "avg_poll_ms": round(self.avg_poll_ms, 2),
            "max_poll_ms": round(self.max_poll_ms, 2),
            "last_poll_at": self.last_poll_at,
        }


class ProcessSampler:
    """CPU/RAM of the NetMon process itself (psutil needs a warm-up call for cpu_percent)."""

    def __init__(self) -> None:
        self._proc = psutil.Process()
        self._proc.cpu_percent(None)
        self._started = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self._proc.oneshot():
            mem = self._proc.memory_info()
            return {
                "pid": self._proc.pid,
                "cpu_percent": self._proc.cpu_percent(None),
                "rss_bytes": mem.rss,
                "threads": self._proc.num_threads(),
                "system_cpu_percent": psutil.cpu_percent(None),
                "system_memory_percent": psutil.virtual_memory().percent,
            }


class PrometheusMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        labels = ("device", "type")
        self.device_up = Gauge("netmon_device_up", "1 if the device answered its last probe",
                               labels, registry=self.registry)  # fmt: skip
        self.latency = Gauge("netmon_device_latency_ms", "Average RTT of the last probe",
                             labels, registry=self.registry)  # fmt: skip
        self.packet_loss = Gauge("netmon_device_packet_loss_percent", "Packet loss of last probe",
                                 labels, registry=self.registry)  # fmt: skip
        self.cpu = Gauge("netmon_device_cpu_percent", "Device CPU utilisation (SNMP)", labels,
                         registry=self.registry)  # fmt: skip
        self.memory = Gauge("netmon_device_memory_percent", "Device memory utilisation (SNMP)",
                            labels, registry=self.registry)  # fmt: skip
        self.throughput = Gauge("netmon_device_throughput_bps", "Device in+out traffic (SNMP)",
                                labels, registry=self.registry)  # fmt: skip
        self.polls = Counter("netmon_polls", "Device polls performed", ("result",),
                             registry=self.registry)  # fmt: skip
        self.poll_duration = Histogram(
            "netmon_poll_duration_seconds", "Duration of a single device poll",
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10), registry=self.registry,
        )  # fmt: skip
        self.alerts_opened = Counter("netmon_alerts_opened", "Alerts opened", ("severity",),
                                     registry=self.registry)  # fmt: skip

    def forget_device(self, name: str, device_type: str) -> None:
        for gauge in (self.device_up, self.latency, self.packet_loss, self.cpu, self.memory,
                      self.throughput):  # fmt: skip
            with contextlib.suppress(KeyError):
                gauge.remove(name, device_type)
