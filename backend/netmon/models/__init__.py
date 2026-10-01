"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from netmon.models.alert import Alert, AlertRule
from netmon.models.device import Device, Interface, Link
from netmon.models.enums import (
    AlertMetric,
    AlertOperator,
    AlertSeverity,
    AlertStatus,
    CheckMethod,
    DeviceStatus,
    DeviceType,
    LinkType,
    SnmpAuthProtocol,
    SnmpPrivProtocol,
    SnmpVersion,
    UserRole,
)
from netmon.models.metric import MetricSample
from netmon.models.user import User

__all__ = [
    "Alert",
    "AlertMetric",
    "AlertOperator",
    "AlertRule",
    "AlertSeverity",
    "AlertStatus",
    "CheckMethod",
    "Device",
    "DeviceStatus",
    "DeviceType",
    "Interface",
    "Link",
    "LinkType",
    "MetricSample",
    "SnmpAuthProtocol",
    "SnmpPrivProtocol",
    "SnmpVersion",
    "User",
    "UserRole",
]
