from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from netmon.db.base import Base, utcnow


class MetricSample(Base):
    """One measurement of a device taken by a single poll cycle.

    A wide row (one column per metric) keeps writes cheap and makes time-bucketed
    aggregation a single ``GROUP BY``.
    """

    __tablename__ = "metric_samples"
    __table_args__ = (sa.Index("ix_metric_samples_device_ts", "device_id", "ts"),)

    id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True
    )
    device_id: Mapped[int] = mapped_column(sa.ForeignKey("devices.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    is_up: Mapped[bool] = mapped_column()
    latency_ms: Mapped[float | None] = mapped_column()
    latency_min_ms: Mapped[float | None] = mapped_column()
    latency_max_ms: Mapped[float | None] = mapped_column()
    jitter_ms: Mapped[float | None] = mapped_column()
    packet_loss: Mapped[float | None] = mapped_column()  # percent 0..100
    cpu_percent: Mapped[float | None] = mapped_column()
    memory_percent: Mapped[float | None] = mapped_column()
    in_bps: Mapped[float | None] = mapped_column()
    out_bps: Mapped[float | None] = mapped_column()
    bandwidth_util: Mapped[float | None] = mapped_column()  # busiest interface, percent
    poll_duration_ms: Mapped[float | None] = mapped_column()
