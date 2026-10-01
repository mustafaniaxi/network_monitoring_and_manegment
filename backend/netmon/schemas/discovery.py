from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from netmon.models import CheckMethod, DeviceType
from netmon.schemas.common import Schema


class ScanRequest(Schema):
    cidr: str = Field(examples=["192.168.1.0/24"])
    method: CheckMethod = CheckMethod.ICMP
    tcp_port: int | None = Field(default=None, ge=1, le=65535)
    snmp_community: str | None = Field(default=None, max_length=255)


class DiscoveredHostRead(Schema):
    ip_address: str
    latency_ms: float | None
    hostname: str | None
    sys_name: str | None
    sys_descr: str | None
    suggested_type: DeviceType
    existing_device_id: int | None


class ScanJobRead(Schema):
    id: str
    cidr: str
    method: CheckMethod
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    total: int
    scanned: int
    found: int
    created_by: str
    created_at: datetime
    finished_at: datetime | None
    error: str | None
    hosts: list[DiscoveredHostRead]


class ImportHost(Schema):
    ip_address: str
    name: str = Field(min_length=1, max_length=120)
    device_type: DeviceType = DeviceType.OTHER


class ImportRequest(Schema):
    hosts: list[ImportHost] = Field(min_length=1, max_length=1024)
    snmp_enabled: bool = False
    snmp_community: str | None = Field(default=None, max_length=255)


class ImportResult(Schema):
    created: list[int]
    skipped: list[str]
