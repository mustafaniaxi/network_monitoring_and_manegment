from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from netmon.db.base import Base, TimestampMixin, str_enum, utcnow
from netmon.models.device import Device
from netmon.models.enums import (
    AlertMetric,
    AlertOperator,
    AlertSeverity,
    AlertStatus,
    DeviceType,
)


class AlertRule(TimestampMixin, Base):
    """Threshold rule evaluated against every new metric sample.

    Scope: a rule applies to one device (``device_id``), to a device type (``device_type``),
    or to all devices when both are null.
    """

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    description: Mapped[str | None] = mapped_column(sa.String(500))
    metric: Mapped[AlertMetric] = mapped_column(str_enum(AlertMetric))
    operator: Mapped[AlertOperator] = mapped_column(
        str_enum(AlertOperator), default=AlertOperator.GT
    )
    threshold: Mapped[float] = mapped_column(default=0.0)
    consecutive: Mapped[int] = mapped_column(default=1)  # breaches required before firing
    severity: Mapped[AlertSeverity] = mapped_column(
        str_enum(AlertSeverity), default=AlertSeverity.WARNING
    )
    device_type: Mapped[DeviceType | None] = mapped_column(str_enum(DeviceType))
    device_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (sa.Index("ix_alerts_device_status", "device_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(sa.ForeignKey("devices.id", ondelete="CASCADE"))
    rule_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("alert_rules.id", ondelete="SET NULL"), index=True
    )
    metric: Mapped[AlertMetric] = mapped_column(str_enum(AlertMetric))
    severity: Mapped[AlertSeverity] = mapped_column(str_enum(AlertSeverity))
    status: Mapped[AlertStatus] = mapped_column(
        str_enum(AlertStatus), default=AlertStatus.ACTIVE, index=True
    )
    title: Mapped[str] = mapped_column(sa.String(255))
    message: Mapped[str] = mapped_column(sa.String(1000))
    value: Mapped[float | None] = mapped_column()
    threshold: Mapped[float | None] = mapped_column()
    triggered_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    # When the condition was first observed (first breaching sample); triggered_at - first
    # breach is the detection delay introduced by the ``consecutive`` setting.
    first_breach_at: Mapped[datetime | None] = mapped_column()
    acknowledged_at: Mapped[datetime | None] = mapped_column()
    acknowledged_by_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column()
    resolution_note: Mapped[str | None] = mapped_column(sa.String(500))

    device: Mapped[Device] = relationship(lazy="joined")
