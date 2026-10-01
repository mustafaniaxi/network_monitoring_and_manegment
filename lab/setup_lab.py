#!/usr/bin/env python3
"""Register the Docker virtual-lab devices and their links in NetMon (idempotent).

python lab/setup_lab.py --api http://localhost:8080 --email admin@example.com --password ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
from netmon_api import ApiError, NetMonClient

COMMUNITY = "netmon-lab"
DEVICES = [
    {"name": "Lab Router", "ip_address": "172.30.0.10", "device_type": "router",
     "snmp_enabled": True, "snmp_community": COMMUNITY},
    {"name": "Lab Switch", "ip_address": "172.30.0.11", "device_type": "switch",
     "snmp_enabled": True, "snmp_community": COMMUNITY},
    {"name": "Lab Web Server", "ip_address": "172.30.0.20", "device_type": "server",
     "check_method": "tcp", "tcp_port": 80, "snmp_enabled": True, "snmp_version": "v3",
     "snmp_v3_username": "netmonv3", "snmp_v3_auth_protocol": "sha",
     "snmp_v3_auth_key": "lab-auth-pass", "snmp_v3_priv_protocol": "aes128",
     "snmp_v3_priv_key": "lab-priv-pass"},
    {"name": "Lab DB Server", "ip_address": "172.30.0.21", "device_type": "server",
     "snmp_enabled": True, "snmp_community": COMMUNITY},
    {"name": "Lab Client", "ip_address": "172.30.0.50", "device_type": "pc",
     "snmp_enabled": True, "snmp_community": COMMUNITY},
]  # fmt: skip
LINKS = [
    ("Lab Router", "Lab Switch"),
    ("Lab Switch", "Lab Web Server"),
    ("Lab Switch", "Lab DB Server"),
    ("Lab Switch", "Lab Client"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8080")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=None,
        help="per-device poll interval in seconds (e.g. 10 for experiments)",
    )
    args = parser.parse_args()

    api = NetMonClient(args.api, args.email, args.password)
    existing = {d["ip_address"]: d for d in api.all_devices()}
    ids: dict[str, int] = {}
    for spec in DEVICES:
        payload = dict(spec, tags=["lab"], location="Virtual lab")
        if args.poll_interval:
            payload["poll_interval_seconds"] = args.poll_interval
        if spec["ip_address"] in existing:
            device = api.patch(f"/devices/{existing[spec['ip_address']]['id']}", payload)
            print(f"updated  {device['name']:<16} {device['ip_address']}")
        else:
            device = api.post("/devices", payload)
            print(f"created  {device['name']:<16} {device['ip_address']}")
        ids[device["name"]] = device["id"]

    for source, target in LINKS:
        try:
            api.post("/topology/links", {"source_id": ids[source], "target_id": ids[target]})
            print(f"linked   {source} -> {target}")
        except ApiError as exc:
            if exc.status != 409:
                raise
    print("lab ready - open the Topology page to see it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
