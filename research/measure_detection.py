#!/usr/bin/env python3
"""Experiment: how quickly does NetMon detect (and clear) a device failure?

Each trial injects a failure into a lab container, then measures

* **detection time** - failure injected -> ``device_down`` alert visible in the API
* **status time**    - failure injected -> device status becomes ``down``
* **recovery time**  - failure removed  -> alert auto-resolved

and records whether the failure was detected at all (availability-detection accuracy).

Failure injection methods:
  disconnect (default) - detach the container from the lab network ("cable unplugged")
  stop                 - stop the container (host powered off)
  command              - run --fail-cmd / --restore-cmd, e.g. for VirtualBox/VMware VMs:
                         --fail-cmd "VBoxManage controlvm VM2 setlinkstate1 off"
                         --restore-cmd "VBoxManage controlvm VM2 setlinkstate1 on"

Example (Docker virtual lab, see docs/virtual-lab.md):
    python research/measure_detection.py --password ... --device "Lab DB Server" \\
        --container netmon-lab-db-1 --trials 20 --out research/results/detection.csv
"""

from __future__ import annotations

import argparse
import csv
import shlex
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from netmon_api import NetMonClient

POLL = 0.25  # seconds between API checks while waiting


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603


def docker(*args: str) -> None:
    run(["docker", *args])


def wait_for(predicate: Any, timeout: float) -> float | None:
    """Poll ``predicate`` until truthy; returns the monotonic timestamp or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return time.monotonic()
        time.sleep(POLL)
    return None


def describe(values: list[float]) -> str:
    if not values:
        return "n=0"
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return (f"n={len(values)} mean={statistics.fmean(values):.2f}s "
            f"median={statistics.median(values):.2f}s sd={sd:.2f}s "
            f"min={ordered[0]:.2f}s p95={p95:.2f}s max={ordered[-1]:.2f}s")  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8080")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", required=True)
    parser.add_argument("--device", required=True, help="device name or id in NetMon")
    parser.add_argument("--container", help="docker container to fail (disconnect/stop)")
    parser.add_argument("--network", default="netmon_lab", help="lab network (disconnect mode)")
    parser.add_argument("--ip", help="container IP to restore (default: device IP)")
    parser.add_argument("--method", choices=["disconnect", "stop", "command"], default="disconnect")
    parser.add_argument("--fail-cmd", help="command that breaks the device (method=command)")
    parser.add_argument("--restore-cmd", help="command that repairs the device (method=command)")
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--cooldown", type=float, default=20)
    parser.add_argument("--out", type=Path, default=Path("research/results/detection.csv"))
    args = parser.parse_args()
    if args.method == "command" and not (args.fail_cmd and args.restore_cmd):
        parser.error("--method command needs --fail-cmd and --restore-cmd")
    if args.method != "command" and not args.container:
        parser.error(f"--method {args.method} needs --container")

    api = NetMonClient(args.api, args.email, args.password)
    device = api.find_device(args.device)
    device_id, ip = device["id"], args.ip or device["ip_address"]
    info = api.get("/system/info")
    interval = device["poll_interval_seconds"] or info["poll_interval_seconds"]
    print(f"device {device['name']} ({ip}); poll interval {interval}s; "
          f"down after {info['down_after_failures']} failures")  # fmt: skip

    def open_down_alert() -> dict[str, Any] | None:
        alerts = api.get("/alerts", device_id=device_id, open_only="true", page_size=50)["items"]
        return next((a for a in alerts if a["metric"] == "device_down"), None)

    def status() -> str:
        return str(api.get(f"/devices/{device_id}")["status"])

    def fail() -> None:
        if args.method == "command":
            run(shlex.split(args.fail_cmd))
        elif args.method == "disconnect":
            docker("network", "disconnect", args.network, args.container)
        else:
            docker("stop", "-t", "0", args.container)

    def restore() -> None:
        if args.method == "command":
            run(shlex.split(args.restore_cmd))
        elif args.method == "disconnect":
            docker("network", "connect", "--ip", ip, args.network, args.container)
        else:
            docker("start", args.container)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for trial in range(1, args.trials + 1):
        if wait_for(lambda: status() in ("up", "degraded") and open_down_alert() is None,
                    args.timeout) is None:  # fmt: skip
            print(f"trial {trial}: device did not return to a healthy state - aborting")
            break

        injected_at = datetime.now(UTC)
        t0 = time.monotonic()
        fail()
        t_status = wait_for(lambda: status() == "down", args.timeout)
        t_alert = wait_for(lambda: open_down_alert() is not None, args.timeout)

        t1 = time.monotonic()
        restore()
        t_resolved = wait_for(lambda: open_down_alert() is None, args.timeout)

        row = {
            "trial": trial,
            "injected_at": injected_at.isoformat(),
            "method": args.method,
            "poll_interval_s": interval,
            "detected": t_alert is not None,
            "detection_s": round(t_alert - t0, 3) if t_alert else None,
            "status_down_s": round(t_status - t0, 3) if t_status else None,
            "recovery_s": round(t_resolved - t1, 3) if t_resolved else None,
        }
        rows.append(row)
        print(f"trial {trial}: detection {row['detection_s']}s, status {row['status_down_s']}s, "
              f"recovery {row['recovery_s']}s")  # fmt: skip
        time.sleep(args.cooldown)

    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["trial"])
        writer.writeheader()
        writer.writerows(rows)

    detected = [r for r in rows if r["detected"]]
    print("\n=== summary ===")
    print(f"detection rate : {len(detected)}/{len(rows)}")
    print(f"detection time : {describe([r['detection_s'] for r in detected])}")
    print(f"recovery time  : {describe([r['recovery_s'] for r in rows if r['recovery_s']])}")
    print(f"raw results    : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
