"""Synthetic network used for demos, UI development and load testing.

Each simulated device has a personality derived from its type: realistic latency ranges, a
diurnal traffic curve (busy office hours), CPU that follows load, occasional packet-loss
bursts, CPU spikes, bandwidth saturation and outages. Devices whose name mentions a database
are deliberately "flaky" so the alerting pipeline has something to report
(``ALERT: Database Server is unreachable.``).
"""

from __future__ import annotations

import hashlib
import ipaddress
import math
import random
import time
from dataclasses import dataclass, field, replace
from datetime import datetime

from netmon.models import CheckMethod, DeviceType
from netmon.services.monitoring.probes import summarise_rtts
from netmon.services.monitoring.types import (
    DeviceTarget,
    InterfaceCounters,
    ProbeResult,
    SnmpCredentials,
    SnmpSnapshot,
)

LATENCY_RANGE: dict[DeviceType, tuple[float, float]] = {
    DeviceType.ROUTER: (0.8, 3.0),
    DeviceType.SWITCH: (0.4, 1.5),
    DeviceType.FIREWALL: (0.8, 2.5),
    DeviceType.SERVER: (0.6, 4.0),
    DeviceType.PC: (1.0, 6.0),
    DeviceType.ACCESS_POINT: (2.0, 12.0),
    DeviceType.PRINTER: (1.5, 8.0),
    DeviceType.CLOUD: (12.0, 35.0),
    DeviceType.OTHER: (1.0, 10.0),
}

CPU_BASE: dict[DeviceType, float] = {
    DeviceType.ROUTER: 18, DeviceType.SWITCH: 12, DeviceType.FIREWALL: 25, DeviceType.SERVER: 35,
    DeviceType.PC: 20, DeviceType.ACCESS_POINT: 15, DeviceType.PRINTER: 5, DeviceType.OTHER: 15,
}  # fmt: skip

# (name, speed Mbps, typical utilisation at peak)
INTERFACES: dict[DeviceType, list[tuple[str, int, float]]] = {
    DeviceType.ROUTER: [("GigabitEthernet0/0", 100, 0.45), ("GigabitEthernet0/1", 1000, 0.08)],
    DeviceType.FIREWALL: [("wan0", 100, 0.40), ("lan0", 1000, 0.06)],
    DeviceType.SWITCH: [(f"GigabitEthernet1/0/{i}", 1000, 0.04 + 0.02 * (i % 3))
                        for i in range(1, 9)] + [("TenGigabitEthernet1/1/1", 10000, 0.03)],
    DeviceType.SERVER: [("eth0", 1000, 0.12)],
    DeviceType.PC: [("Ethernet0", 1000, 0.02)],
    DeviceType.ACCESS_POINT: [("eth0", 1000, 0.05), ("wlan0", 300, 0.25)],
    DeviceType.PRINTER: [("eth0", 100, 0.01)],
    DeviceType.OTHER: [("eth0", 100, 0.05)],
}  # fmt: skip

SYS_DESCR: dict[DeviceType, str] = {
    DeviceType.ROUTER: "Cisco IOS Software, C2900 Software (C2900-UNIVERSALK9-M), Version 15.7",
    DeviceType.SWITCH: "Cisco IOS Software, C2960X Software (C2960X-UNIVERSALK9-M), Version 15.2",
    DeviceType.FIREWALL: "pfSense 2.7.2-RELEASE amd64 FreeBSD 14.0",
    DeviceType.SERVER: "Linux srv 6.8.0-45-generic #45-Ubuntu SMP x86_64",
    DeviceType.PC: "Hardware: Intel64 Family 6 Model 154 - Software: Windows Version 6.3",
    DeviceType.ACCESS_POINT: "UniFi AP-AC-Pro 6.6.77 Linux",
    DeviceType.PRINTER: "HP ETHERNET MULTI-ENVIRONMENT, HP LaserJet Pro M404dn",
    DeviceType.CLOUD: "",
    DeviceType.OTHER: "Embedded Linux device",
}


def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def diurnal_factor(now: datetime) -> float:
    """0.15 at night rising to 1.0 around 13:00 local; weekends are quieter."""
    hour = now.hour + now.minute / 60
    day = max(0.0, math.sin(math.pi * (hour - 7) / 12)) if 7 <= hour <= 19 else 0.0
    weekend = 0.45 if now.weekday() >= 5 else 1.0
    return 0.15 + 0.85 * day * weekend


@dataclass
class _IfaceState:
    counters: InterfaceCounters
    peak_util: float


@dataclass
class _DeviceState:
    rng: random.Random
    device_type: DeviceType
    flaky: bool
    base_latency: float
    outage_left: int = 0
    loss_left: int = 0
    cpu_spike_left: int = 0
    saturation_left: int = 0
    cpu: float = 20.0
    memory: float = 50.0
    boot_time: float = field(default_factory=lambda: time.time() - random.uniform(3, 90) * 86400)
    last_poll: float = field(default_factory=time.monotonic)
    interfaces: list[_IfaceState] = field(default_factory=list)


class SimulatedBackend:
    name = "simulation"

    def __init__(self, seed: int | None = None) -> None:
        self._seed = seed if seed is not None else random.randrange(2**32)
        self._devices: dict[int, _DeviceState] = {}

    # ------------------------------------------------------------------ device state
    def _state(self, target: DeviceTarget) -> _DeviceState:
        state = self._devices.get(target.id)
        if state is None or state.device_type != target.device_type:
            rng = random.Random(stable_seed(self._seed, target.id, target.name))
            lo, hi = LATENCY_RANGE.get(target.device_type, (1.0, 10.0))
            lowered = target.name.lower()
            state = _DeviceState(
                rng=rng,
                device_type=target.device_type,
                flaky="database" in lowered or lowered.startswith("db"),
                base_latency=rng.uniform(lo, hi),
                cpu=CPU_BASE.get(target.device_type, 15) * rng.uniform(0.7, 1.3),
                memory=rng.uniform(35, 70),
            )
            for idx, (name, speed, peak) in enumerate(
                INTERFACES.get(target.device_type, []), start=1
            ):
                state.interfaces.append(
                    _IfaceState(
                        counters=InterfaceCounters(
                            if_index=idx, name=name, if_type=6, admin_status="up",
                            oper_status="up", speed_mbps=speed,
                            in_octets=rng.randrange(10**9, 10**12),
                            out_octets=rng.randrange(10**9, 10**12), counters_64bit=True,
                        ),
                        peak_util=peak * rng.uniform(0.6, 1.4),
                    )
                )  # fmt: skip
            self._devices[target.id] = state
        return state

    def _advance_events(self, s: _DeviceState) -> None:
        rng = s.rng
        if s.outage_left > 0:
            s.outage_left -= 1
            if s.outage_left == 0 and rng.random() < 0.5:
                s.boot_time = time.time()  # came back after a reboot
        elif rng.random() < (0.03 if s.flaky else 0.0008):
            s.outage_left = rng.randint(3, 10)
        if s.loss_left > 0:
            s.loss_left -= 1
        elif rng.random() < (0.03 if s.device_type == DeviceType.ACCESS_POINT else 0.008):
            s.loss_left = rng.randint(2, 6)
        if s.cpu_spike_left > 0:
            s.cpu_spike_left -= 1
        elif s.device_type in (DeviceType.SERVER, DeviceType.FIREWALL) and rng.random() < 0.01:
            s.cpu_spike_left = rng.randint(3, 8)
        if s.saturation_left > 0:
            s.saturation_left -= 1
        elif s.device_type in (DeviceType.ROUTER, DeviceType.FIREWALL) and rng.random() < 0.006:
            s.saturation_left = rng.randint(3, 8)

    # ------------------------------------------------------------------ backend API
    async def probe(self, target: DeviceTarget) -> ProbeResult:
        s = self._state(target)
        self._advance_events(s)
        if s.outage_left > 0:
            return ProbeResult.down("request timed out (simulated outage)", packets_sent=3)
        load = diurnal_factor(datetime.now())
        rtts = [
            max(0.05, s.base_latency * (1 + 0.6 * load) * s.rng.lognormvariate(0, 0.25))
            for _ in range(3)
        ]
        if s.loss_left > 0:
            rtts = rtts[: s.rng.choice([1, 2])]
            rtts = [r * s.rng.uniform(4, 12) for r in rtts]
        return summarise_rtts(rtts, sent=3)

    async def snmp_poll(self, target: DeviceTarget) -> SnmpSnapshot:
        s = self._state(target)
        now_mono = time.monotonic()
        elapsed = max(1.0, now_mono - s.last_poll)
        s.last_poll = now_mono
        load = diurnal_factor(datetime.now())

        base_cpu = CPU_BASE.get(target.device_type, 15)
        target_cpu = base_cpu * (0.6 + 0.8 * load)
        s.cpu += (target_cpu - s.cpu) * 0.3 + s.rng.gauss(0, 2.5)
        cpu = s.rng.uniform(92, 99) if s.cpu_spike_left > 0 else s.cpu
        s.memory = min(88.0, max(20.0, s.memory + s.rng.gauss(0, 0.6)))

        interfaces: list[InterfaceCounters] = []
        for i, iface in enumerate(s.interfaces):
            c = iface.counters
            speed_bps = (c.speed_mbps or 100) * 1_000_000
            util = iface.peak_util * load * s.rng.lognormvariate(0, 0.2)
            if s.saturation_left > 0 and i == 0:
                util = s.rng.uniform(0.86, 0.97)
            util = min(util, 0.99)
            in_bps = speed_bps * util
            out_bps = in_bps * s.rng.uniform(0.15, 0.6)
            c.in_octets = int((c.in_octets or 0) + in_bps * elapsed / 8) % 2**64
            c.out_octets = int((c.out_octets or 0) + out_bps * elapsed / 8) % 2**64
            interfaces.append(replace(c))

        return SnmpSnapshot(
            sys_name=target.name.lower().replace(" ", "-"),
            sys_descr=SYS_DESCR.get(target.device_type, "Simulated device"),
            sys_object_id="1.3.6.1.4.1.8072.3.2.10",
            uptime_seconds=int(time.time() - s.boot_time),
            cpu_percent=round(min(100.0, max(0.5, cpu)), 2),
            memory_percent=round(s.memory, 2),
            interfaces=interfaces,
            requests=1,
        )

    async def discover(self, host: str, method: CheckMethod, tcp_port: int | None) -> ProbeResult:
        try:
            last_octet = int(ipaddress.ip_address(host).packed[-1])
        except ValueError:
            return ProbeResult.down("invalid address")
        rng = random.Random(stable_seed(self._seed, host))
        alive = last_octet in (1, 2, 3, 5, 10, 11, 12, 20, 250) or rng.random() < 0.08
        if not alive:
            return ProbeResult.down("no reply", packets_sent=1)
        rtt = rng.uniform(0.4, 9.0)
        return ProbeResult(is_up=True, latency_ms=round(rtt, 3), min_ms=rtt, max_ms=rtt,
                           jitter_ms=0.0, packet_loss=0.0, packets_sent=1)  # fmt: skip

    async def snmp_system(self, host: str, creds: SnmpCredentials) -> dict[str, object]:
        last_octet = int(ipaddress.ip_address(host).packed[-1])
        guess = {1: DeviceType.ROUTER, 2: DeviceType.SWITCH, 3: DeviceType.FIREWALL,
                 5: DeviceType.ACCESS_POINT, 250: DeviceType.PRINTER}.get(last_octet)  # fmt: skip
        if guess is None:
            guess = DeviceType.SERVER if last_octet < 50 else DeviceType.PC
        return {
            "sys_descr": SYS_DESCR[guess],
            "sys_object_id": "1.3.6.1.4.1.8072.3.2.10",
            "uptime_seconds": 86400 * (last_octet % 30 + 1),
            "sys_name": f"{guess.value.replace('_', '-')}-{last_octet}",
        }

    async def close(self) -> None:
        self._devices.clear()
