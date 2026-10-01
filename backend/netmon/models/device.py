from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from netmon.db.base import Base, Counter, TimestampMixin, str_enum
from netmon.models.enums import (
    CheckMethod,
    DeviceStatus,
    DeviceType,
    LinkType,
    SnmpAuthProtocol,
    SnmpPrivProtocol,
    SnmpVersion,
)


class Device(TimestampMixin, Base):
    """A monitored network element (router, switch, server, ...)."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(120), unique=True)
    ip_address: Mapped[str] = mapped_column(sa.String(255), unique=True, index=True)
    device_type: Mapped[DeviceType] = mapped_column(str_enum(DeviceType), default=DeviceType.OTHER)
    vendor: Mapped[str | None] = mapped_column(sa.String(120))
    model: Mapped[str | None] = mapped_column(sa.String(120))
    location: Mapped[str | None] = mapped_column(sa.String(120))
    description: Mapped[str | None] = mapped_column(sa.Text)
    mac_address: Mapped[str | None] = mapped_column(sa.String(32))
    tags: Mapped[list[str]] = mapped_column(sa.JSON, default=list)

    # --- monitoring configuration
    is_monitored: Mapped[bool] = mapped_column(default=True)
    poll_interval_seconds: Mapped[int | None] = mapped_column()  # None -> global default
    check_method: Mapped[CheckMethod] = mapped_column(
        str_enum(CheckMethod), default=CheckMethod.ICMP
    )
    tcp_port: Mapped[int | None] = mapped_column()

    # --- SNMP configuration (secrets are write-only through the API)
    snmp_enabled: Mapped[bool] = mapped_column(default=False)
    snmp_version: Mapped[SnmpVersion] = mapped_column(
        str_enum(SnmpVersion), default=SnmpVersion.V2C
    )
    snmp_port: Mapped[int] = mapped_column(default=161)
    snmp_community: Mapped[str | None] = mapped_column(sa.String(255))
    snmp_v3_username: Mapped[str | None] = mapped_column(sa.String(255))
    snmp_v3_auth_protocol: Mapped[SnmpAuthProtocol] = mapped_column(
        str_enum(SnmpAuthProtocol), default=SnmpAuthProtocol.NONE
    )
    snmp_v3_auth_key: Mapped[str | None] = mapped_column(sa.String(255))
    snmp_v3_priv_protocol: Mapped[SnmpPrivProtocol] = mapped_column(
        str_enum(SnmpPrivProtocol), default=SnmpPrivProtocol.NONE
    )
    snmp_v3_priv_key: Mapped[str | None] = mapped_column(sa.String(255))

    # --- live state (maintained by the monitoring engine)
    status: Mapped[DeviceStatus] = mapped_column(
        str_enum(DeviceStatus), default=DeviceStatus.UNKNOWN, index=True
    )
    status_changed_at: Mapped[datetime | None] = mapped_column()
    last_checked_at: Mapped[datetime | None] = mapped_column()
    last_seen_at: Mapped[datetime | None] = mapped_column()
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_latency_ms: Mapped[float | None] = mapped_column()
    last_packet_loss: Mapped[float | None] = mapped_column()
    last_cpu_percent: Mapped[float | None] = mapped_column()
    last_memory_percent: Mapped[float | None] = mapped_column()
    last_in_bps: Mapped[float | None] = mapped_column()
    last_out_bps: Mapped[float | None] = mapped_column()
    last_bandwidth_util: Mapped[float | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(sa.String(500))
    sys_name: Mapped[str | None] = mapped_column(sa.String(255))
    sys_descr: Mapped[str | None] = mapped_column(sa.Text)
    sys_object_id: Mapped[str | None] = mapped_column(sa.String(255))
    uptime_seconds: Mapped[int | None] = mapped_column(sa.BigInteger)

    # --- topology canvas position (None -> auto layout)
    topology_x: Mapped[float | None] = mapped_column()
    topology_y: Mapped[float | None] = mapped_column()

    interfaces: Mapped[list[Interface]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Device {self.name} {self.ip_address} {self.status}>"


class Interface(Base):
    """Latest known state of a device interface (from IF-MIB)."""

    __tablename__ = "interfaces"
    __table_args__ = (sa.UniqueConstraint("device_id", "if_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        sa.ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    if_index: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(sa.String(255), default="")
    alias: Mapped[str | None] = mapped_column(sa.String(255))
    if_type: Mapped[int | None] = mapped_column()
    admin_status: Mapped[str] = mapped_column(sa.String(16), default="unknown")
    oper_status: Mapped[str] = mapped_column(sa.String(16), default="unknown")
    speed_mbps: Mapped[float | None] = mapped_column()
    in_octets: Mapped[int | None] = mapped_column(Counter())
    out_octets: Mapped[int | None] = mapped_column(Counter())
    counters_64bit: Mapped[bool] = mapped_column(default=False)
    counters_at: Mapped[datetime | None] = mapped_column()
    in_bps: Mapped[float | None] = mapped_column()
    out_bps: Mapped[float | None] = mapped_column()
    utilization_percent: Mapped[float | None] = mapped_column()
    updated_at: Mapped[datetime | None] = mapped_column()

    device: Mapped[Device] = relationship(back_populates="interfaces")


class Link(TimestampMixin, Base):
    """A physical or logical connection between two devices (topology edge)."""

    __tablename__ = "links"
    __table_args__ = (
        sa.UniqueConstraint("source_id", "target_id", name="uq_links_source_target"),
        sa.CheckConstraint("source_id <> target_id", name="no_self_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        sa.ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[int] = mapped_column(
        sa.ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    link_type: Mapped[LinkType] = mapped_column(str_enum(LinkType), default=LinkType.ETHERNET)
    source_interface: Mapped[str | None] = mapped_column(sa.String(64))
    target_interface: Mapped[str | None] = mapped_column(sa.String(64))
    bandwidth_mbps: Mapped[float | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(sa.String(255))
