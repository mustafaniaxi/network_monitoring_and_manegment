from __future__ import annotations

from datetime import datetime

from netmon.schemas.common import Schema


class DeviceCounts(Schema):
    total: int
    unmonitored: int
    up: int
    down: int
    degraded: int
    unknown: int


class AlertCounts(Schema):
    active: int
    acknowledged: int
    info: int
    warning: int
    critical: int


class DashboardSummary(Schema):
    devices: DeviceCounts
    by_type: dict[str, int]
    availability_24h: float | None
    samples_24h: int
    avg_latency_ms_1h: float | None
    avg_packet_loss_1h: float | None
    throughput_bps: float
    avg_bandwidth_util: float | None
    alerts: AlertCounts


class NetworkPoint(Schema):
    ts: datetime
    latency_ms: float | None
    packet_loss: float | None
    availability: float | None
    in_bps: float | None
    out_bps: float | None
    devices: int


class NetworkSeries(Schema):
    range: str
    bucket_seconds: int
    points: list[NetworkPoint]


class AvailabilityRow(Schema):
    device_id: int
    name: str
    ip_address: str
    device_type: str
    status: str
    samples: int
    availability: float | None
    avg_latency_ms: float | None
    max_latency_ms: float | None
    avg_packet_loss: float | None
    avg_jitter_ms: float | None
    incidents: int
    downtime_seconds: int
    mttr_seconds: int | None


class HeatmapPeak(Schema):
    day: int
    hour: int
    bps: float


class TrafficHeatmap(Schema):
    days: list[str]
    matrix_bps: list[list[float | None]]
    peak: HeatmapPeak | None


class BottleneckDevice(Schema):
    device_id: int
    name: str
    device_type: str
    avg_bandwidth_util: float | None
    max_bandwidth_util: float | None
    avg_cpu_percent: float | None
    max_cpu_percent: float | None
    avg_latency_ms: float | None
    avg_packet_loss: float | None


class BottleneckInterface(Schema):
    device_id: int
    device: str | None
    interface: str
    speed_mbps: float | None
    in_bps: float | None
    out_bps: float | None
    utilization_percent: float | None


class Bottlenecks(Schema):
    devices: list[BottleneckDevice]
    interfaces: list[BottleneckInterface]


class DegradationRow(Schema):
    device_id: int
    name: str
    latency_before_ms: float | None
    latency_after_ms: float | None
    latency_change_percent: float | None
    packet_loss_before: float | None
    packet_loss_after: float | None
    availability_before: float | None
    availability_after: float | None
    degraded: bool


class Distribution(Schema):
    count: int
    mean: float | None
    median: float | None
    min: float | None
    max: float | None


class DetectionReport(Schema):
    outages: int
    detection_delay_seconds: Distribution
    time_to_recovery_seconds: Distribution


class PollerStatsRead(Schema):
    started_at: datetime
    uptime_seconds: int
    polls_total: int
    polls_down: int
    poll_errors: int
    probe_packets: int
    snmp_requests: int
    estimated_bytes: int
    estimated_bandwidth_bps: float
    polls_per_minute: float
    avg_poll_ms: float
    max_poll_ms: float
    last_poll_at: datetime | None


class ProcessStats(Schema):
    pid: int
    cpu_percent: float
    rss_bytes: int
    threads: int
    system_cpu_percent: float
    system_memory_percent: float


class SystemStats(Schema):
    running: bool
    backend: str
    monitored_devices: int
    in_flight: int
    websocket_clients: int
    poller: PollerStatsRead
    process: ProcessStats


class SystemInfo(Schema):
    name: str
    version: str
    environment: str
    monitor_mode: str
    monitoring_enabled: bool
    poll_interval_seconds: int
    down_after_failures: int
    metrics_retention_days: int
    notifications: dict[str, bool]
