#!/usr/bin/env python3
"""Experiment: what does monitoring itself cost (server CPU/RAM, network traffic)?

Samples ``GET /api/v1/system/stats`` for a fixed duration and reports, over the window:
polls per minute, probe packets/s, SNMP requests/s, estimated monitoring bandwidth, and
the NetMon process CPU / resident memory.

Scaling experiments: in simulation mode, ``--add-devices N`` registers N synthetic devices
(tagged "bench") before measuring and ``--cleanup`` removes them afterwards, so overhead can
be measured for 10, 50, 100, 500 ... devices with identical conditions.

    python research/measure_overhead.py --password ... --duration 300 --add-devices 100 --cleanup
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from pathlib import Path
from typing import Any

from netmon_api import ApiError, NetMonClient


def add_bench_devices(api: NetMonClient, count: int) -> list[int]:
    ids = []
    for i in range(count):
        ip = f"10.200.{i // 250}.{i % 250 + 1}"
        try:
            device = api.post("/devices", {"name": f"bench-{i:04d}", "ip_address": ip,
                                           "device_type": "server", "snmp_enabled": True,
                                           "tags": ["bench"]})  # fmt: skip
            ids.append(device["id"])
        except ApiError as exc:
            if exc.status != 409:
                raise
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8080")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", required=True)
    parser.add_argument("--duration", type=float, default=300, help="seconds to measure")
    parser.add_argument("--interval", type=float, default=5, help="seconds between samples")
    parser.add_argument("--warmup", type=float, default=30, help="seconds to wait before measuring")
    parser.add_argument("--add-devices", type=int, default=0)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("research/results/overhead.csv"))
    args = parser.parse_args()

    api = NetMonClient(args.api, args.email, args.password)
    created = add_bench_devices(api, args.add_devices) if args.add_devices else []
    if created:
        print(f"added {len(created)} bench devices; warming up {args.warmup:.0f}s")
    time.sleep(args.warmup if created else 0)

    samples: list[dict[str, Any]] = []
    end = time.monotonic() + args.duration
    while time.monotonic() < end:
        s = api.get("/system/stats")
        samples.append({
            "t": round(time.time(), 1),
            "devices": s["monitored_devices"],
            "polls_total": s["poller"]["polls_total"],
            "probe_packets": s["poller"]["probe_packets"],
            "snmp_requests": s["poller"]["snmp_requests"],
            "estimated_bytes": s["poller"]["estimated_bytes"],
            "avg_poll_ms": s["poller"]["avg_poll_ms"],
            "process_cpu_percent": s["process"]["cpu_percent"],
            "process_rss_mb": round(s["process"]["rss_bytes"] / 2**20, 1),
            "system_cpu_percent": s["process"]["system_cpu_percent"],
        })  # fmt: skip
        time.sleep(args.interval)

    if args.cleanup:
        for device_id in created:
            api.delete(f"/devices/{device_id}")
        print(f"removed {len(created)} bench devices")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(samples[0]))
        writer.writeheader()
        writer.writerows(samples)

    first, last = samples[0], samples[-1]
    span = max(1e-9, last["t"] - first["t"])
    delta = {k: last[k] - first[k] for k in ("polls_total", "probe_packets", "snmp_requests",
                                             "estimated_bytes")}  # fmt: skip
    cpu = [s["process_cpu_percent"] for s in samples[1:]] or [0.0]
    print("\n=== monitoring overhead ===")
    print(f"devices monitored : {last['devices']}")
    print(f"window            : {span:.0f}s ({len(samples)} samples)")
    print(f"polls per minute  : {delta['polls_total'] * 60 / span:.1f}")
    print(f"probe packets/s   : {delta['probe_packets'] / span:.2f}")
    print(f"SNMP requests/s   : {delta['snmp_requests'] / span:.2f}")
    kbps = delta["estimated_bytes"] * 8 / span / 1000
    print(f"monitoring traffic: {kbps:.2f} kbit/s (estimated)")
    print(f"avg poll duration : {statistics.fmean(s['avg_poll_ms'] for s in samples):.1f} ms")
    print(f"process CPU       : mean {statistics.fmean(cpu):.1f}% max {max(cpu):.1f}%")
    print(f"process memory    : max {max(s['process_rss_mb'] for s in samples):.1f} MiB")
    print(f"raw samples       : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
