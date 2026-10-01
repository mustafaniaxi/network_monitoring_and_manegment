from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from netmon.models import (
    AlertMetric,
    AlertOperator,
    AlertSeverity,
    AlertStatus,
    DeviceType,
)
from netmon.schemas.common import Schema


class AlertRead(Schema):
    id: int
    device_id: int
    device_name: str | None = None
    rule_id: int | None
    metric: AlertMetric
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    value: float | None
    threshold: float | None
    triggered_at: datetime
    first_breach_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by_id: int | None
    resolved_at: datetime | None
    resolution_note: str | None

    @model_validator(mode="before")
    @classmethod
    def _device_name(cls, data: object) -> object:
        device = getattr(data, "device", None)
        if device is not None:
            return {
                **{k: getattr(data, k) for k in cls.model_fields if hasattr(data, k)},
                "device_name": device.name,
            }
        return data


class AlertAction(Schema):
    note: str | None = Field(default=None, max_length=500)


class AlertSummary(Schema):
    active: int
    acknowledged: int
    resolved_24h: int
    by_severity: dict[str, int]


class AlertRuleBase(Schema):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    metric: AlertMetric
    operator: AlertOperator = AlertOperator.GT
    threshold: float = 0.0
    consecutive: int = Field(default=1, ge=1, le=100)
    severity: AlertSeverity = AlertSeverity.WARNING
    device_type: DeviceType | None = None
    device_id: int | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _scope(self) -> Self:
        if self.device_type is not None and self.device_id is not None:
            raise ValueError("a rule is scoped to either a device or a device type, not both")
        if self.metric == AlertMetric.DEVICE_DOWN:
            self.operator, self.threshold = AlertOperator.GTE, 1.0
        return self


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    operator: AlertOperator | None = None
    threshold: float | None = None
    consecutive: int | None = Field(default=None, ge=1, le=100)
    severity: AlertSeverity | None = None
    enabled: bool | None = None


class AlertRuleRead(AlertRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime
