from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from netmon.models import (
    CheckMethod,
    DeviceStatus,
    DeviceType,
    SnmpAuthProtocol,
    SnmpPrivProtocol,
    SnmpVersion,
)
from netmon.schemas.common import Schema, validate_host


class DeviceFields(Schema):
    """Fields shared by create and update (all optional here, required ones on create)."""

    device_type: DeviceType | None = None
    vendor: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    mac_address: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None

    is_monitored: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    check_method: CheckMethod | None = None
    tcp_port: int | None = Field(default=None, ge=1, le=65535)

    snmp_enabled: bool | None = None
    snmp_version: SnmpVersion | None = None
    snmp_port: int | None = Field(default=None, ge=1, le=65535)
    # Secrets: write-only. Omit to keep the stored value, send "" to clear it.
    snmp_community: str | None = Field(default=None, max_length=255)
    snmp_v3_username: str | None = Field(default=None, max_length=255)
    snmp_v3_auth_protocol: SnmpAuthProtocol | None = None
    snmp_v3_auth_key: str | None = Field(default=None, max_length=255)
    snmp_v3_priv_protocol: SnmpPrivProtocol | None = None
    snmp_v3_priv_key: str | None = Field(default=None, max_length=255)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        if tags is None:
            return None
        return sorted({t.strip().lower()[:32] for t in tags if t.strip()})

    @field_validator("snmp_v3_auth_key", "snmp_v3_priv_key")
    @classmethod
    def _v3_key_length(cls, key: str | None) -> str | None:
        if key and len(key) < 8:
            raise ValueError("SNMPv3 keys must be at least 8 characters")
        return key


class DeviceCreate(DeviceFields):
    name: str = Field(min_length=1, max_length=120)
    ip_address: str = Field(min_length=1, max_length=255)
    device_type: DeviceType = DeviceType.OTHER
    is_monitored: bool = True
    check_method: CheckMethod = CheckMethod.ICMP
    snmp_enabled: bool = False
    snmp_version: SnmpVersion = SnmpVersion.V2C
    snmp_port: int = Field(default=161, ge=1, le=65535)

    @field_validator("ip_address")
    @classmethod
    def _host(cls, value: str) -> str:
        return validate_host(value)

    @model_validator(mode="after")
    def _check_method(self) -> Self:
        if self.check_method == CheckMethod.TCP and not self.tcp_port:
            raise ValueError("tcp_port is required when check_method is 'tcp'")
        return self


class DeviceUpdate(DeviceFields):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    ip_address: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("ip_address")
    @classmethod
    def _host(cls, value: str | None) -> str | None:
        return None if value is None else validate_host(value)


class DeviceRead(Schema):
    id: int
    name: str
    ip_address: str
    device_type: DeviceType
    vendor: str | None
    model: str | None
    location: str | None
    description: str | None
    mac_address: str | None
    tags: list[str]

    is_monitored: bool
    poll_interval_seconds: int | None
    check_method: CheckMethod
    tcp_port: int | None

    snmp_enabled: bool
    snmp_version: SnmpVersion
    snmp_port: int
    snmp_v3_username: str | None
    snmp_v3_auth_protocol: SnmpAuthProtocol
    snmp_v3_priv_protocol: SnmpPrivProtocol
    snmp_community_set: bool = False
    snmp_v3_auth_key_set: bool = False
    snmp_v3_priv_key_set: bool = False

    status: DeviceStatus
    status_changed_at: datetime | None
    last_checked_at: datetime | None
    last_seen_at: datetime | None
    consecutive_failures: int
    last_latency_ms: float | None
    last_packet_loss: float | None
    last_cpu_percent: float | None
    last_memory_percent: float | None
    last_in_bps: float | None
    last_out_bps: float | None
    last_bandwidth_util: float | None
    last_error: str | None
    sys_name: str | None
    sys_descr: str | None
    uptime_seconds: int | None

    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _secret_flags(cls, data: object) -> object:
        # Expose whether a secret is configured without ever returning it.
        if hasattr(data, "snmp_community"):
            return {
                **{k: getattr(data, k) for k in cls.model_fields if hasattr(data, k)},
                "snmp_community_set": bool(data.snmp_community),
                "snmp_v3_auth_key_set": bool(getattr(data, "snmp_v3_auth_key", None)),
                "snmp_v3_priv_key_set": bool(getattr(data, "snmp_v3_priv_key", None)),
            }
        return data


class InterfaceRead(Schema):
    id: int
    if_index: int
    name: str
    alias: str | None
    if_type: int | None
    admin_status: str
    oper_status: str
    speed_mbps: float | None
    in_bps: float | None
    out_bps: float | None
    utilization_percent: float | None
    updated_at: datetime | None


class MetricPoint(Schema):
    ts: datetime
    latency_ms: float | None
    latency_max_ms: float | None
    jitter_ms: float | None
    packet_loss: float | None
    availability: float | None
    cpu_percent: float | None
    memory_percent: float | None
    in_bps: float | None
    out_bps: float | None
    bandwidth_util: float | None
    samples: int


class DeviceMetrics(Schema):
    device_id: int
    range: str
    bucket_seconds: int
    points: list[MetricPoint]
