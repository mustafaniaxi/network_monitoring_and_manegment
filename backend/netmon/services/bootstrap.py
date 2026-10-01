"""First-run initialisation and demo data."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from netmon.core.config import Settings
from netmon.core.security import hash_password
from netmon.models import (
    AlertRule,
    CheckMethod,
    Device,
    DeviceType,
    Link,
    LinkType,
    User,
    UserRole,
)
from netmon.services.alerting.defaults import DEFAULT_RULES

log = logging.getLogger(__name__)


async def ensure_first_admin(session: AsyncSession, settings: Settings) -> User | None:
    if await session.scalar(select(func.count()).select_from(User)):
        return None
    admin = User(
        email=settings.first_admin_email.lower(),
        full_name="Administrator",
        hashed_password=hash_password(settings.first_admin_password.get_secret_value()),
        role=UserRole.ADMIN,
    )
    session.add(admin)
    await session.commit()
    log.warning(
        "created initial administrator %s - change the password after first login",
        admin.email,
    )
    return admin


async def ensure_default_rules(session: AsyncSession) -> int:
    if await session.scalar(select(func.count()).select_from(AlertRule)):
        return 0
    session.add_all(AlertRule(**rule) for rule in DEFAULT_RULES)
    await session.commit()
    return len(DEFAULT_RULES)


# A small office network matching the reference design (router, switch, servers, AP, PCs).
DEMO_DEVICES: list[dict[str, object]] = [
    {"name": "Internet (Cloudflare DNS)", "ip_address": "1.1.1.1", "device_type": DeviceType.CLOUD,
     "location": "WAN"},
    {"name": "Edge Router", "ip_address": "192.168.1.1", "device_type": DeviceType.ROUTER,
     "vendor": "Cisco", "model": "ISR 2911", "location": "Server room", "snmp_enabled": True},
    {"name": "Core Switch", "ip_address": "192.168.1.2", "device_type": DeviceType.SWITCH,
     "vendor": "Cisco", "model": "Catalyst 2960-X", "location": "Server room",
     "snmp_enabled": True},
    {"name": "Office Access Point", "ip_address": "192.168.1.5",
     "device_type": DeviceType.ACCESS_POINT, "vendor": "Ubiquiti", "model": "UniFi AP AC Pro",
     "location": "Open office", "snmp_enabled": True},
    {"name": "Web Server", "ip_address": "192.168.1.10", "device_type": DeviceType.SERVER,
     "vendor": "Dell", "model": "PowerEdge R650", "location": "Server room",
     "snmp_enabled": True, "check_method": CheckMethod.TCP, "tcp_port": 443},
    {"name": "Database Server", "ip_address": "192.168.1.11", "device_type": DeviceType.SERVER,
     "vendor": "Dell", "model": "PowerEdge R750", "location": "Server room",
     "snmp_enabled": True},
    {"name": "PC-01 Reception", "ip_address": "192.168.1.101", "device_type": DeviceType.PC,
     "location": "Reception"},
    {"name": "PC-02 Accounting", "ip_address": "192.168.1.102", "device_type": DeviceType.PC,
     "location": "Accounting"},
    {"name": "Office Printer", "ip_address": "192.168.1.250", "device_type": DeviceType.PRINTER,
     "vendor": "HP", "model": "LaserJet Pro M404dn", "location": "Open office",
     "snmp_enabled": True},
]  # fmt: skip

DEMO_LINKS: list[tuple[str, str, LinkType]] = [
    ("Internet (Cloudflare DNS)", "Edge Router", LinkType.WAN),
    ("Edge Router", "Core Switch", LinkType.ETHERNET),
    ("Core Switch", "Office Access Point", LinkType.ETHERNET),
    ("Core Switch", "Web Server", LinkType.ETHERNET),
    ("Core Switch", "Database Server", LinkType.ETHERNET),
    ("Core Switch", "Office Printer", LinkType.ETHERNET),
    ("Core Switch", "PC-01 Reception", LinkType.ETHERNET),
    ("Office Access Point", "PC-02 Accounting", LinkType.WIRELESS),
]


async def seed_demo(session: AsyncSession) -> int:
    """Insert the demo network if no devices exist yet. Returns the number of devices added."""
    if await session.scalar(select(func.count()).select_from(Device)):
        return 0
    by_name: dict[str, Device] = {}
    for spec in DEMO_DEVICES:
        device = Device(snmp_community="public", tags=["demo"], **spec)
        session.add(device)
        by_name[device.name] = device
    await session.flush()
    for source, target, link_type in DEMO_LINKS:
        session.add(
            Link(source_id=by_name[source].id, target_id=by_name[target].id, link_type=link_type)
        )
    await session.commit()
    return len(by_name)
