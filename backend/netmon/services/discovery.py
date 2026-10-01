"""Network discovery: concurrent ping/TCP sweep of a subnet with optional SNMP fingerprinting.

Scans run as background jobs so the API stays responsive; clients poll the job for progress.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from netmon.core.config import Settings
from netmon.db.base import utcnow
from netmon.models import CheckMethod, DeviceType, SnmpVersion
from netmon.services.monitoring.backends import MonitorBackend
from netmon.services.monitoring.types import SnmpCredentials

log = logging.getLogger(__name__)

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
MAX_JOBS_KEPT = 20

_FINGERPRINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("fortigate", "pfsense", "opnsense", "adaptive security appliance", "palo alto",
      "firewall", "sophos"), DeviceType.FIREWALL),
    (("access point", "unifi ap", "airos", "aironet", "wap"), DeviceType.ACCESS_POINT),
    (("printer", "laserjet", "jetdirect", "officejet", "epson", "brother", "kyocera",
      "ricoh", "lexmark"), DeviceType.PRINTER),
    (("catalyst", "switch", "procurve", "nexus", "edgeswitch", "c2960", "c3750", "c9300"),
     DeviceType.SWITCH),
    (("cisco ios", "routeros", "mikrotik", "junos", "vyos", "edgeos", "router"),
     DeviceType.ROUTER),
    (("windows",), DeviceType.PC),
    (("linux", "freebsd", "ubuntu", "debian", "centos", "red hat", "vmware esxi"),
     DeviceType.SERVER),
]  # fmt: skip


def guess_device_type(sys_descr: str | None, ip: str) -> DeviceType:
    if sys_descr:
        text = sys_descr.lower()
        for keywords, device_type in _FINGERPRINTS:
            if any(k in text for k in keywords):
                return device_type
    # Heuristic: the first usable address of a subnet is usually the gateway.
    if ip.endswith(".1"):
        return DeviceType.ROUTER
    return DeviceType.OTHER


@dataclass(slots=True)
class DiscoveredHost:
    ip_address: str
    latency_ms: float | None
    hostname: str | None = None
    sys_name: str | None = None
    sys_descr: str | None = None
    suggested_type: DeviceType = DeviceType.OTHER
    existing_device_id: int | None = None


@dataclass
class DiscoveryJob:
    id: str
    cidr: str
    method: CheckMethod
    tcp_port: int | None
    snmp_community: str | None
    created_by: str
    total: int
    status: JobStatus = "pending"
    scanned: int = 0
    created_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    error: str | None = None
    hosts: list[DiscoveredHost] = field(default_factory=list)
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class DiscoveryError(ValueError):
    pass


def parse_network(cidr: str, max_hosts: int) -> list[str]:
    try:
        network = ipaddress.ip_network(cidr.strip(), strict=False)
    except ValueError as exc:
        raise DiscoveryError(f"invalid network: {exc}") from exc
    if network.version != 4:
        raise DiscoveryError("only IPv4 sweeps are supported")
    if network.num_addresses > max_hosts + 2:
        raise DiscoveryError(
            f"{network} contains {network.num_addresses} addresses; the limit is {max_hosts} "
            "(adjust NETMON_DISCOVERY_MAX_HOSTS)"
        )
    hosts = [str(h) for h in network.hosts()]
    return hosts or [str(network.network_address)]


async def reverse_dns(ip: str, max_wait: float = 1.0) -> str | None:
    loop = asyncio.get_running_loop()
    try:
        host, _ = await asyncio.wait_for(loop.getnameinfo((ip, 0), socket.NI_NAMEREQD), max_wait)
    except (TimeoutError, OSError, socket.gaierror):
        return None
    return host if host and host != ip else None


class DiscoveryManager:
    def __init__(self, settings: Settings, backend: MonitorBackend) -> None:
        self.settings = settings
        self.backend = backend
        self._jobs: dict[str, DiscoveryJob] = {}

    def list_jobs(self) -> list[DiscoveryJob]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> DiscoveryJob | None:
        return self._jobs.get(job_id)

    def start(
        self,
        cidr: str,
        *,
        method: CheckMethod = CheckMethod.ICMP,
        tcp_port: int | None = None,
        snmp_community: str | None = None,
        created_by: str = "",
        known: dict[str, int] | None = None,
    ) -> DiscoveryJob:
        hosts = parse_network(cidr, self.settings.discovery_max_hosts)
        if method == CheckMethod.TCP and not tcp_port:
            raise DiscoveryError("tcp_port is required for TCP discovery")
        job = DiscoveryJob(
            id=uuid.uuid4().hex[:12],
            cidr=cidr,
            method=method,
            tcp_port=tcp_port,
            snmp_community=snmp_community,
            created_by=created_by,
            total=len(hosts),
        )
        self._jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job, hosts, known or {}))
        self._prune()
        return job

    def cancel(self, job_id: str) -> DiscoveryJob | None:
        job = self._jobs.get(job_id)
        if job and job.task and not job.task.done():
            job.task.cancel()
        return job

    def _prune(self) -> None:
        finished = [j for j in self.list_jobs() if j.status not in ("pending", "running")]
        for job in finished[MAX_JOBS_KEPT:]:
            self._jobs.pop(job.id, None)

    async def _run(self, job: DiscoveryJob, hosts: list[str], known: dict[str, int]) -> None:
        job.status = "running"
        semaphore = asyncio.Semaphore(self.settings.discovery_concurrency)
        creds = (
            SnmpCredentials(version=SnmpVersion.V2C, community=job.snmp_community)
            if job.snmp_community
            else None
        )

        async def scan(ip: str) -> None:
            async with semaphore:
                try:
                    result = await self.backend.discover(ip, job.method, job.tcp_port)
                    if result.is_up:
                        host = DiscoveredHost(
                            ip_address=ip,
                            latency_ms=result.latency_ms,
                            existing_device_id=known.get(ip),
                        )
                        host.hostname = await reverse_dns(ip)
                        if creds is not None:
                            try:
                                info = await self.backend.snmp_system(ip, creds)
                                host.sys_name = str(info.get("sys_name") or "") or None
                                host.sys_descr = str(info.get("sys_descr") or "") or None
                            except Exception:  # no agent / wrong community - not fatal
                                log.debug("SNMP fingerprint of %s failed", ip, exc_info=True)
                        host.suggested_type = guess_device_type(host.sys_descr, ip)
                        job.hosts.append(host)
                finally:
                    job.scanned += 1

        try:
            await asyncio.gather(*(scan(ip) for ip in hosts))
            job.hosts.sort(key=lambda h: ipaddress.ip_address(h.ip_address))
            job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
        except Exception as exc:
            log.exception("discovery job %s failed", job.id)
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = utcnow()
