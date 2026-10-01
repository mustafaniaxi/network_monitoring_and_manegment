"""Threshold-based alert engine.

For every new metric sample the engine evaluates the rules that apply to the device:

* **Scope & precedence** - for each metric only the most specific rules are used:
  device-specific rules override device-type rules, which override global rules. This lets an
  operator raise the latency threshold for a single WAN link without touching the defaults.
* **Debouncing** - a rule must be breached on ``consecutive`` successive samples before an
  alert is opened, which suppresses one-off spikes.
* **De-duplication** - at most one open (active or acknowledged) alert exists per
  (rule, device); repeated breaches update nothing until it is resolved.
* **Auto-resolution** - the first sample that no longer breaches resolves the alert.
"""

from __future__ import annotations

import operator
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from netmon.db.base import utcnow
from netmon.models import (
    Alert,
    AlertMetric,
    AlertOperator,
    AlertRule,
    AlertStatus,
    Device,
    MetricSample,
)

_OPERATORS: dict[AlertOperator, Callable[[float, float], bool]] = {
    AlertOperator.GT: operator.gt,
    AlertOperator.GTE: operator.ge,
    AlertOperator.LT: operator.lt,
    AlertOperator.LTE: operator.le,
}
_OPERATOR_SYMBOL = {AlertOperator.GT: ">", AlertOperator.GTE: ">=", AlertOperator.LT: "<",
                    AlertOperator.LTE: "<="}  # fmt: skip

METRIC_LABELS: dict[AlertMetric, tuple[str, str]] = {
    AlertMetric.DEVICE_DOWN: ("availability", ""),
    AlertMetric.LATENCY: ("latency", " ms"),
    AlertMetric.PACKET_LOSS: ("packet loss", "%"),
    AlertMetric.CPU: ("CPU utilisation", "%"),
    AlertMetric.MEMORY: ("memory utilisation", "%"),
    AlertMetric.BANDWIDTH: ("bandwidth utilisation", "%"),
}

OPEN_STATUSES = (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)


@dataclass(slots=True)
class AlertTransition:
    kind: Literal["opened", "resolved"]
    alert: Alert
    device_name: str


def metric_value(metric: AlertMetric, sample: MetricSample) -> float | None:
    if metric == AlertMetric.DEVICE_DOWN:
        return 0.0 if sample.is_up else 1.0
    if not sample.is_up:
        return None  # an unreachable device is reported once, by the reachability rule
    value = getattr(sample, metric.value)
    return None if value is None else float(value)


def is_breached(value: float, op: AlertOperator, threshold: float) -> bool:
    return _OPERATORS[op](value, threshold)


def format_alert(rule: AlertRule, device: Device, value: float) -> tuple[str, str]:
    if rule.metric == AlertMetric.DEVICE_DOWN:
        return "Device unreachable", f"ALERT: {device.name} is unreachable."
    label, unit = METRIC_LABELS[rule.metric]
    symbol = _OPERATOR_SYMBOL[rule.operator]
    return (
        rule.name,
        f"ALERT: {device.name} {label} is {value:.1f}{unit} "
        f"(threshold {symbol} {rule.threshold:g}{unit}).",
    )


def format_resolution(alert: Alert, device: Device) -> str:
    if alert.metric == AlertMetric.DEVICE_DOWN:
        return f"RESOLVED: {device.name} is reachable again."
    label, _unit = METRIC_LABELS[alert.metric]
    return f"RESOLVED: {device.name} {label} is back to normal."


def select_effective_rules(rules: Sequence[AlertRule], device: Device) -> list[AlertRule]:
    """Apply scope precedence: device > device type > global, per metric."""
    by_metric: dict[AlertMetric, list[tuple[int, AlertRule]]] = defaultdict(list)
    for rule in rules:
        if rule.device_id is not None:
            if rule.device_id != device.id:
                continue
            specificity = 2
        elif rule.device_type is not None:
            if rule.device_type != device.device_type:
                continue
            specificity = 1
        else:
            specificity = 0
        by_metric[rule.metric].append((specificity, rule))
    effective: list[AlertRule] = []
    for candidates in by_metric.values():
        best = max(spec for spec, _ in candidates)
        effective.extend(rule for spec, rule in candidates if spec == best)
    return effective


class AlertEngine:
    def __init__(self) -> None:
        # (rule_id, device_id) -> (consecutive breaches, time of first breach)
        self._streaks: dict[tuple[int, int], tuple[int, datetime]] = {}

    def reset_device(self, device_id: int) -> None:
        for key in [k for k in self._streaks if k[1] == device_id]:
            del self._streaks[key]

    async def evaluate(
        self, session: AsyncSession, device: Device, sample: MetricSample
    ) -> list[AlertTransition]:
        rules = (
            await session.scalars(
                select(AlertRule).where(
                    AlertRule.enabled.is_(True),
                    or_(AlertRule.device_id.is_(None), AlertRule.device_id == device.id),
                )
            )
        ).all()
        open_alerts = {
            alert.rule_id: alert
            for alert in (
                await session.scalars(
                    select(Alert).where(
                        Alert.device_id == device.id,
                        Alert.status.in_(OPEN_STATUSES),
                        Alert.rule_id.is_not(None),
                    )
                )
            ).all()
        }

        transitions: list[AlertTransition] = []
        effective = select_effective_rules(rules, device)
        effective_ids = {rule.id for rule in effective}

        for rule in effective:
            value = metric_value(rule.metric, sample)
            if value is None:
                continue  # metric not collected for this device / sample
            key = (rule.id, device.id)
            existing = open_alerts.get(rule.id)
            if is_breached(value, rule.operator, rule.threshold):
                count, first_breach = self._streaks.get(key, (0, sample.ts))
                count += 1
                self._streaks[key] = (count, first_breach)
                if existing is None and count >= rule.consecutive:
                    title, message = format_alert(rule, device, value)
                    alert = Alert(
                        device_id=device.id,
                        rule_id=rule.id,
                        metric=rule.metric,
                        severity=rule.severity,
                        status=AlertStatus.ACTIVE,
                        title=title,
                        message=message,
                        value=value,
                        threshold=rule.threshold,
                        triggered_at=sample.ts,
                        first_breach_at=first_breach,
                    )
                    alert.device = device
                    session.add(alert)
                    transitions.append(AlertTransition("opened", alert, device.name))
            else:
                self._streaks.pop(key, None)
                if existing is not None:
                    self._resolve(existing, device, sample.ts)
                    transitions.append(AlertTransition("resolved", existing, device.name))

        # Alerts whose rule no longer applies (scope changed, overridden) are closed too.
        for rule_id, alert in open_alerts.items():
            if rule_id not in effective_ids:
                self._resolve(alert, device, sample.ts, note="Rule no longer applies")
                transitions.append(AlertTransition("resolved", alert, device.name))
        return transitions

    @staticmethod
    def _resolve(alert: Alert, device: Device, at: datetime, note: str | None = None) -> None:
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = at
        alert.resolution_note = note or format_resolution(alert, device)


async def resolve_open_alerts(
    session: AsyncSession, *, note: str, rule_id: int | None = None, device_id: int | None = None
) -> int:
    """Close open alerts for a rule or device (used when rules/devices are disabled)."""
    stmt = select(Alert).where(Alert.status.in_(OPEN_STATUSES))
    if rule_id is not None:
        stmt = stmt.where(Alert.rule_id == rule_id)
    if device_id is not None:
        stmt = stmt.where(Alert.device_id == device_id)
    alerts = (await session.scalars(stmt)).all()
    now = utcnow()
    for alert in alerts:
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = now
        alert.resolution_note = note
    return len(alerts)
