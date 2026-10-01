"""Availability probes: ICMP echo (ping) and TCP connect."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import statistics
import time
from itertools import pairwise

import icmplib

from netmon.services.monitoring.types import ProbeResult

log = logging.getLogger(__name__)

_RTT_RE = re.compile(r"time[=<]([\d.]+)\s*ms")


def summarise_rtts(rtts: list[float], sent: int) -> ProbeResult:
    if not rtts:
        return ProbeResult.down("no reply", packets_sent=sent)
    jitter = statistics.mean(abs(b - a) for a, b in pairwise(rtts)) if len(rtts) > 1 else 0.0
    return ProbeResult(
        is_up=True,
        latency_ms=round(statistics.mean(rtts), 3),
        min_ms=round(min(rtts), 3),
        max_ms=round(max(rtts), 3),
        jitter_ms=round(jitter, 3),
        packet_loss=round(100.0 * (sent - len(rtts)) / sent, 2),
        packets_sent=sent,
    )


class IcmpProber:
    """ICMP echo using ``icmplib``.

    Privilege handling:
    * running as root (or with ``CAP_NET_RAW``) -> raw sockets;
    * otherwise unprivileged datagram ICMP sockets, which need
      ``net.ipv4.ping_group_range`` to include the process group (set by default in Docker);
    * if neither is permitted, fall back to the system ``ping`` binary.
    """

    def __init__(
        self, count: int, interval: float, timeout: float, privileged: bool | None = None
    ) -> None:
        self.count = count
        self.interval = interval
        self.timeout = timeout
        self.privileged = (
            privileged if privileged is not None else hasattr(os, "geteuid") and os.geteuid() == 0
        )
        self._use_subprocess = False

    async def probe(self, host: str, count: int | None = None) -> ProbeResult:
        count = count or self.count
        if not self._use_subprocess:
            try:
                result = await icmplib.async_ping(
                    host,
                    count=count,
                    interval=self.interval,
                    timeout=self.timeout,
                    privileged=self.privileged,
                )
            except icmplib.SocketPermissionError:
                if shutil.which("ping") is None:
                    return ProbeResult.down("ICMP not permitted and no ping binary available")
                log.warning("ICMP sockets not permitted; falling back to the system ping binary")
                self._use_subprocess = True
            except icmplib.NameLookupError:
                return ProbeResult.down(f"cannot resolve host {host!r}")
            except (icmplib.ICMPLibError, OSError) as exc:
                return ProbeResult.down(f"icmp error: {exc}")
            else:
                return summarise_rtts([float(r) for r in result.rtts], result.packets_sent)
        return await self._probe_subprocess(host, count)

    async def _probe_subprocess(self, host: str, count: int) -> ProbeResult:
        timeout_s = max(1, round(self.timeout))
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-n", "-c", str(count), "-W", str(timeout_s), host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=count * (timeout_s + 1))
        except (TimeoutError, OSError) as exc:
            return ProbeResult.down(f"ping failed: {exc}", packets_sent=count)
        rtts = [float(m) for m in _RTT_RE.findall(out.decode(errors="replace"))]
        return summarise_rtts(rtts, count)


class TcpProber:
    """Measures TCP handshake time to a service port (for hosts that block ICMP)."""

    def __init__(self, timeout: float, attempts: int = 3) -> None:
        self.timeout = timeout
        self.attempts = attempts

    async def probe(self, host: str, port: int, attempts: int | None = None) -> ProbeResult:
        attempts = attempts or self.attempts
        rtts: list[float] = []
        last_error = "connection failed"
        for _ in range(attempts):
            start = time.perf_counter()
            try:
                _reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=self.timeout
                )
            except TimeoutError:
                last_error = f"tcp/{port} timed out"
                continue
            except OSError as exc:
                last_error = f"tcp/{port}: {exc.strerror or exc}"
                continue
            rtts.append((time.perf_counter() - start) * 1000)
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        result = summarise_rtts(rtts, attempts)
        if not result.is_up:
            result.error = last_error
        return result
