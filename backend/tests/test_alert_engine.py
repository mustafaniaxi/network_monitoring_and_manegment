"""Unit tests of rule selection and evaluation logic (no database)."""

from __future__ import annotations

import pytest

from netmon.models import (
    AlertMetric,
    AlertOperator,
    AlertRule,
    AlertSeverity,
    Device,
    DeviceType,
    MetricSample,
)
from netmon.services.alerting.engine import (
    format_alert,
    is_breached,
    metric_value,
    select_effective_rules,
)


def rule(rule_id: int, metric=AlertMetric.LATENCY, **kw) -> AlertRule:
    r = AlertRule(
        name=f"r{rule_id}", metric=metric, operator=kw.pop("operator", AlertOperator.GT),
        threshold=kw.pop("threshold", 100.0), consecutive=1, severity=AlertSeverity.WARNING,
        enabled=True, **kw,
    )  # fmt: skip
    r.id = rule_id
    return r


@pytest.fixture
def device() -> Device:
    d = Device(name="WAN Router", ip_address="10.0.0.1", device_type=DeviceType.ROUTER)
    d.id = 7
    return d


@pytest.mark.parametrize(
    ("value", "op", "threshold", "expected"),
    [
        (5, AlertOperator.GT, 5, False),
        (5, AlertOperator.GTE, 5, True),
        (4, AlertOperator.LT, 5, True),
        (5, AlertOperator.LTE, 5, True),
        (6, AlertOperator.LTE, 5, False),
    ],
)
def test_is_breached(value, op, threshold, expected):
    assert is_breached(value, op, threshold) is expected


def test_device_specific_rule_overrides_type_and_global(device):
    global_rule = rule(1)
    type_rule = rule(2, device_type=DeviceType.ROUTER)
    device_rule = rule(3, device_id=7)
    other_device_rule = rule(4, device_id=99)
    cpu_rule = rule(5, metric=AlertMetric.CPU)
    effective = select_effective_rules(
        [global_rule, type_rule, device_rule, other_device_rule, cpu_rule], device
    )
    assert {r.id for r in effective} == {3, 5}


def test_type_rule_overrides_global_rule(device):
    effective = select_effective_rules(
        [rule(1), rule(2, device_type=DeviceType.ROUTER), rule(3, device_type=DeviceType.SWITCH)],
        device,
    )
    assert [r.id for r in effective] == [2]


def test_metric_value_handles_down_devices():
    down = MetricSample(is_up=False, packet_loss=100.0, latency_ms=None)
    assert metric_value(AlertMetric.DEVICE_DOWN, down) == 1.0
    assert metric_value(AlertMetric.PACKET_LOSS, down) is None
    upsample = MetricSample(is_up=True, packet_loss=0.0, latency_ms=12.5, cpu_percent=None)
    assert metric_value(AlertMetric.DEVICE_DOWN, upsample) == 0.0
    assert metric_value(AlertMetric.LATENCY, upsample) == 12.5
    assert metric_value(AlertMetric.CPU, upsample) is None


def test_alert_messages(device):
    title, message = format_alert(rule(1, metric=AlertMetric.DEVICE_DOWN), device, 1.0)
    assert (title, message) == ("Device unreachable", "ALERT: WAN Router is unreachable.")
    _, message = format_alert(rule(2, threshold=200), device, 250.123)
    assert message == "ALERT: WAN Router latency is 250.1 ms (threshold > 200 ms)."
