"""Application factory and lifespan management."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from netmon import __version__
from netmon.api.v1.router import api_router
from netmon.core.config import Settings, get_settings
from netmon.core.logging import configure_logging
from netmon.core.security import LoginThrottle
from netmon.db.base import Base
from netmon.db.session import create_engine, create_session_factory
from netmon.services.bootstrap import ensure_default_rules, ensure_first_admin
from netmon.services.discovery import DiscoveryManager
from netmon.services.events import EventHub
from netmon.services.monitoring.backends import MonitorBackend
from netmon.services.monitoring.service import MonitoringService

log = logging.getLogger("netmon")

OPENAPI_DESCRIPTION = """
Centralised monitoring of routers, switches, servers, PCs, access points and printers.

* **Device management** - inventory with SNMP v1/v2c/v3 credentials
* **Real-time monitoring** - ICMP/TCP availability, latency, jitter, packet loss; SNMP CPU,
  memory, interface status and bandwidth
* **Alerts** - threshold rules with debouncing, auto-resolution, webhook and e-mail delivery
* **Discovery, topology, historical analytics and reports**

Authenticate with `POST /api/v1/auth/login` (or the *Authorize* button) and send the token as
`Authorization: Bearer <token>`.
"""


def create_app(settings: Settings | None = None, backend: MonitorBackend | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        hub = EventHub()
        monitor = MonitoringService(settings, session_factory, hub, backend=backend)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.hub = hub
        app.state.monitor = monitor
        app.state.discovery = DiscoveryManager(settings, monitor.backend)
        app.state.login_throttle = LoginThrottle(
            settings.login_max_attempts, settings.login_lockout_seconds
        )

        if settings.db_auto_create:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        if settings.uses_default_secret:
            log.warning("NETMON_SECRET_KEY is not set - using an insecure development key")
        async with session_factory() as session:
            await ensure_first_admin(session, settings)
            await ensure_default_rules(session)
        if settings.monitoring_enabled:
            await monitor.start()
        log.info("%s %s ready (%s mode)", settings.app_name, __version__, settings.monitor_mode)
        try:
            yield
        finally:
            await monitor.stop()
            await engine.dispose()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=OPENAPI_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith(settings.api_prefix):
            log.debug(
                "%s %s -> %s (%.1f ms)", request.method, request.url.path,
                response.status_code, elapsed_ms,
                extra={"request_id": request_id},
            )  # fmt: skip
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"], summary="Readiness probe (database + engine)")
    async def ready(request: Request) -> JSONResponse:
        checks: dict[str, str] = {}
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc.__class__.__name__}"
        monitor: MonitoringService = request.app.state.monitor
        checks["monitoring"] = (
            "ok" if monitor.running else ("disabled" if not settings.monitoring_enabled else "down")
        )
        healthy = checks["database"] == "ok" and checks["monitoring"] != "down"
        return JSONResponse(
            {"status": "ok" if healthy else "degraded", "version": __version__, "checks": checks},
            status_code=200 if healthy else 503,
        )

    if settings.prometheus_enabled:

        @app.get("/metrics", tags=["health"], summary="Prometheus metrics", include_in_schema=False)
        async def metrics(request: Request) -> PlainTextResponse:
            registry = request.app.state.monitor.prometheus.registry
            return PlainTextResponse(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app


def app_factory() -> FastAPI:  # pragma: no cover - used by `uvicorn --factory`
    return create_app()
