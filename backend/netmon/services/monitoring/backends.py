"""Monitoring backends: where the measurements come from.

``LiveBackend`` talks to the real network (ICMP/TCP/SNMP). ``SimulatedBackend`` (see
``simulation.py``) produces realistic synthetic data so the full stack can be demonstrated
without lab equipment.
"""

from __future__ import annotations

from typing import Protocol

from netmon.core.config import Settings
from netmon.models import CheckMethod
from netmon.services.monitoring.probes import IcmpProber, TcpProber
from netmon.services.monitoring.snmp import SnmpClient
from netmon.services.monitoring.types import (
    DeviceTarget,
    ProbeResult,
    SnmpCredentials,
    SnmpSnapshot,
)


class MonitorBackend(Protocol):
    name: str

    async def probe(self, target: DeviceTarget) -> ProbeResult: ...

    async def snmp_poll(self, target: DeviceTarget) -> SnmpSnapshot: ...

    async def discover(
        self, host: str, method: CheckMethod, tcp_port: int | None
    ) -> ProbeResult: ...

    async def snmp_system(self, host: str, creds: SnmpCredentials) -> dict[str, object]: ...

    async def close(self) -> None: ...


class LiveBackend:
    name = "live"

    def __init__(self, settings: Settings) -> None:
        self.icmp = IcmpProber(
            count=settings.icmp_count,
            interval=settings.icmp_interval,
            timeout=settings.icmp_timeout,
            privileged=settings.icmp_privileged,
        )
        self.tcp = TcpProber(timeout=settings.tcp_timeout, attempts=settings.icmp_count)
        self.snmp = SnmpClient(timeout=settings.snmp_timeout, retries=settings.snmp_retries)
        self.discovery_timeout = settings.discovery_timeout

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        if target.check_method == CheckMethod.TCP and target.tcp_port:
            return await self.tcp.probe(target.host, target.tcp_port)
        return await self.icmp.probe(target.host)

    async def snmp_poll(self, target: DeviceTarget) -> SnmpSnapshot:
        assert target.snmp is not None
        return await self.snmp.poll(target.host, target.snmp)

    async def discover(self, host: str, method: CheckMethod, tcp_port: int | None) -> ProbeResult:
        if method == CheckMethod.TCP and tcp_port:
            return await TcpProber(timeout=self.discovery_timeout, attempts=1).probe(host, tcp_port)
        return await self.icmp.probe(host, count=1)

    async def snmp_system(self, host: str, creds: SnmpCredentials) -> dict[str, object]:
        return await self.snmp.system_info(host, creds)

    async def close(self) -> None:
        self.snmp.close()


def create_backend(settings: Settings) -> MonitorBackend:
    if settings.monitor_mode == "simulation":
        from netmon.services.monitoring.simulation import SimulatedBackend

        return SimulatedBackend(seed=settings.simulation_seed)
    return LiveBackend(settings)
