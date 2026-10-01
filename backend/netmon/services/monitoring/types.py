"""Plain data structures passed between the probes, the poller and the persistence layer.

They are deliberately decoupled from the ORM so probes can run concurrently without sharing
database sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netmon.models import (
    CheckMethod,
    Device,
    DeviceType,
    SnmpAuthProtocol,
    SnmpPrivProtocol,
    SnmpVersion,
)


@dataclass(frozen=True, slots=True)
class SnmpCredentials:
    version: SnmpVersion = SnmpVersion.V2C
    port: int = 161
    community: str | None = None
    v3_username: str | None = None
    v3_auth_protocol: SnmpAuthProtocol = SnmpAuthProtocol.NONE
    v3_auth_key: str | None = None
    v3_priv_protocol: SnmpPrivProtocol = SnmpPrivProtocol.NONE
    v3_priv_key: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceTarget:
    """Everything a probe needs to know about a device."""

    id: int
    name: str
    host: str
    device_type: DeviceType
    check_method: CheckMethod = CheckMethod.ICMP
    tcp_port: int | None = None
    snmp: SnmpCredentials | None = None
    poll_interval: int = 30

    @classmethod
    def from_device(cls, device: Device, default_interval: int) -> DeviceTarget:
        snmp = None
        if device.snmp_enabled:
            snmp = SnmpCredentials(
                version=device.snmp_version,
                port=device.snmp_port,
                community=device.snmp_community,
                v3_username=device.snmp_v3_username,
                v3_auth_protocol=device.snmp_v3_auth_protocol,
                v3_auth_key=device.snmp_v3_auth_key,
                v3_priv_protocol=device.snmp_v3_priv_protocol,
                v3_priv_key=device.snmp_v3_priv_key,
            )
        return cls(
            id=device.id,
            name=device.name,
            host=device.ip_address,
            device_type=device.device_type,
            check_method=device.check_method,
            tcp_port=device.tcp_port,
            snmp=snmp,
            poll_interval=device.poll_interval_seconds or default_interval,
        )


@dataclass(slots=True)
class ProbeResult:
    """Availability / latency measurement (ICMP echo or TCP connect)."""

    is_up: bool
    latency_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    jitter_ms: float | None = None
    packet_loss: float = 100.0  # percent
    packets_sent: int = 0
    error: str | None = None

    @classmethod
    def down(cls, error: str, packets_sent: int = 0) -> ProbeResult:
        return cls(is_up=False, packet_loss=100.0, packets_sent=packets_sent, error=error)


@dataclass(slots=True)
class InterfaceCounters:
    if_index: int
    name: str
    alias: str | None = None
    if_type: int | None = None
    admin_status: str = "unknown"
    oper_status: str = "unknown"
    speed_mbps: float | None = None
    in_octets: int | None = None
    out_octets: int | None = None
    counters_64bit: bool = False

    @property
    def is_loopback(self) -> bool:
        return self.if_type == 24 or self.name.lower().startswith("lo")


@dataclass(slots=True)
class SnmpSnapshot:
    sys_name: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    uptime_seconds: int | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    interfaces: list[InterfaceCounters] = field(default_factory=list)
    requests: int = 0  # SNMP PDUs exchanged (monitoring-overhead accounting)
