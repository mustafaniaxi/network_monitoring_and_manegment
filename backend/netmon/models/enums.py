"""Domain enumerations shared by models, schemas and services."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"  # full control including user management
    OPERATOR = "operator"  # manage devices, topology, alerts and rules
    VIEWER = "viewer"  # read-only


class DeviceType(StrEnum):
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    SERVER = "server"
    PC = "pc"
    ACCESS_POINT = "access_point"
    PRINTER = "printer"
    CLOUD = "cloud"  # upstream / internet reachability target
    OTHER = "other"


class DeviceStatus(StrEnum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class CheckMethod(StrEnum):
    ICMP = "icmp"
    TCP = "tcp"


class SnmpVersion(StrEnum):
    V1 = "v1"
    V2C = "v2c"
    V3 = "v3"


class SnmpAuthProtocol(StrEnum):
    NONE = "none"
    MD5 = "md5"
    SHA = "sha"
    SHA256 = "sha256"
    SHA512 = "sha512"


class SnmpPrivProtocol(StrEnum):
    NONE = "none"
    DES = "des"
    AES128 = "aes128"
    AES256 = "aes256"


class LinkType(StrEnum):
    ETHERNET = "ethernet"
    FIBER = "fiber"
    WIRELESS = "wireless"
    VPN = "vpn"
    WAN = "wan"


class AlertMetric(StrEnum):
    DEVICE_DOWN = "device_down"
    LATENCY = "latency_ms"
    PACKET_LOSS = "packet_loss"
    CPU = "cpu_percent"
    MEMORY = "memory_percent"
    BANDWIDTH = "bandwidth_util"


class AlertOperator(StrEnum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "warning": 1, "critical": 2}[self.value]


class AlertStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
