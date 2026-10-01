"""Shared fixtures.

Tests run against in-memory SQLite by default. Set ``NETMON_TEST_DATABASE_URL`` (e.g. to a
PostgreSQL URL, as CI does) to run the same suite against another database.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from netmon.core.config import Settings
from netmon.db.base import Base
from netmon.main import create_app
from netmon.models import CheckMethod
from netmon.services.monitoring.service import MonitoringService
from netmon.services.monitoring.types import (
    DeviceTarget,
    ProbeResult,
    SnmpCredentials,
    SnmpSnapshot,
)

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "admin-password-1"


@dataclass
class FakeBackend:
    """Programmable monitoring backend: tests decide what each host 'answers'."""

    name: str = "fake"
    probes: dict[str, ProbeResult] = field(default_factory=dict)
    snmp: dict[str, SnmpSnapshot] = field(default_factory=dict)
    alive: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        self.calls.append(target.host)
        return self.probes.get(
            target.host,
            ProbeResult(is_up=True, latency_ms=1.0, min_ms=0.8, max_ms=1.2, jitter_ms=0.1,
                        packet_loss=0.0, packets_sent=3),
        )  # fmt: skip

    async def snmp_poll(self, target: DeviceTarget) -> SnmpSnapshot:
        if target.host not in self.snmp:
            raise RuntimeError("No SNMP response received before timeout")
        return self.snmp[target.host]

    async def discover(self, host: str, method: CheckMethod, tcp_port: int | None) -> ProbeResult:
        if host in self.alive:
            return ProbeResult(is_up=True, latency_ms=0.5, packet_loss=0.0, packets_sent=1)
        return ProbeResult.down("no reply", packets_sent=1)

    async def snmp_system(self, host: str, creds: SnmpCredentials) -> dict[str, object]:
        return {"sys_name": f"host-{host}", "sys_descr": "Cisco IOS Software, C2960X switch"}

    async def close(self) -> None:
        pass


def up(latency: float = 1.0, loss: float = 0.0) -> ProbeResult:
    return ProbeResult(is_up=True, latency_ms=latency, min_ms=latency, max_ms=latency,
                       jitter_ms=0.0, packet_loss=loss, packets_sent=3)  # fmt: skip


def down() -> ProbeResult:
    return ProbeResult.down("request timed out", packets_sent=3)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url=os.environ.get("NETMON_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
        db_auto_create=True,
        monitoring_enabled=False,
        prometheus_enabled=True,
        secret_key=SecretStr("test-secret-key-that-is-long-enough-0123456789"),
        first_admin_email=ADMIN_EMAIL,
        first_admin_password=SecretStr(ADMIN_PASSWORD),
        login_max_attempts=3,
        down_after_failures=2,
        log_level="WARNING",
    )


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
async def app(settings: Settings, backend: FakeBackend) -> AsyncIterator[FastAPI]:
    application = create_app(settings, backend=backend)
    async with application.router.lifespan_context(application):
        yield application
        if not settings.is_sqlite:  # leave a clean schema for the next test on a real server
            async with application.state.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    async with app.state.session_factory() as s:
        yield s


@pytest.fixture
def monitor(app: FastAPI) -> MonitoringService:
    service: MonitoringService = app.state.monitor
    return service


async def login(client: httpx.AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    return await login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def make_user(
    client: httpx.AsyncClient, admin_headers: dict[str, str], role: str
) -> dict[str, str]:
    email = f"{role}@test.local"
    resp = await client.post(
        "/users",
        json={"email": email, "password": "password-123", "role": role, "full_name": role},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return await login(client, email, "password-123")


@pytest.fixture
async def viewer_headers(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> dict[str, str]:
    return await make_user(client, admin_headers, "viewer")


@pytest.fixture
async def operator_headers(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> dict[str, str]:
    return await make_user(client, admin_headers, "operator")


async def create_device(
    client: httpx.AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Core Router",
        "ip_address": "10.0.0.1",
        "device_type": "router",
    }
    payload.update(overrides)
    resp = await client.post("/devices", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data: dict[str, object] = resp.json()
    return data
