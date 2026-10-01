"""Built-in alert rules created on first start-up (editable afterwards)."""

from __future__ import annotations

from typing import Any

from netmon.models import AlertMetric, AlertOperator, AlertSeverity

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "Device unreachable",
        "description": "Device does not answer availability probes.",
        "metric": AlertMetric.DEVICE_DOWN,
        "operator": AlertOperator.GTE,
        "threshold": 1,
        "consecutive": 2,
        "severity": AlertSeverity.CRITICAL,
    },
    {
        "name": "High packet loss",
        "description": "More than 20% of probe packets are lost.",
        "metric": AlertMetric.PACKET_LOSS,
        "operator": AlertOperator.GT,
        "threshold": 20,
        "consecutive": 2,
        "severity": AlertSeverity.WARNING,
    },
    {
        "name": "High latency",
        "description": "Average round-trip time above 200 ms.",
        "metric": AlertMetric.LATENCY,
        "operator": AlertOperator.GT,
        "threshold": 200,
        "consecutive": 3,
        "severity": AlertSeverity.WARNING,
    },
    {
        "name": "High CPU utilisation",
        "description": "CPU load above 90%.",
        "metric": AlertMetric.CPU,
        "operator": AlertOperator.GT,
        "threshold": 90,
        "consecutive": 2,
        "severity": AlertSeverity.CRITICAL,
    },
    {
        "name": "High memory utilisation",
        "description": "Memory usage above 90%.",
        "metric": AlertMetric.MEMORY,
        "operator": AlertOperator.GT,
        "threshold": 90,
        "consecutive": 3,
        "severity": AlertSeverity.WARNING,
    },
    {
        "name": "High bandwidth utilisation",
        "description": "Busiest interface above 80% of its capacity.",
        "metric": AlertMetric.BANDWIDTH,
        "operator": AlertOperator.GT,
        "threshold": 80,
        "consecutive": 2,
        "severity": AlertSeverity.WARNING,
    },
]
