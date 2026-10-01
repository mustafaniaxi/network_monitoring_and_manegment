from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select

from netmon import __version__
from netmon.api.deps import CurrentUser, MonitorDep, SessionDep, SettingsDep, authenticate_token
from netmon.models import Device
from netmon.schemas.analytics import SystemInfo, SystemStats

log = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/system/info", response_model=SystemInfo)
async def system_info(_: CurrentUser, settings: SettingsDep) -> SystemInfo:
    return SystemInfo(
        name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        monitor_mode=settings.monitor_mode,
        monitoring_enabled=settings.monitoring_enabled,
        poll_interval_seconds=settings.poll_interval_seconds,
        down_after_failures=settings.down_after_failures,
        metrics_retention_days=settings.metrics_retention_days,
        notifications={
            "webhook": bool(settings.alert_webhook_url),
            "email": bool(settings.smtp_host and settings.smtp_to),
        },
    )


@router.get("/system/stats", response_model=SystemStats, summary="Monitoring overhead")
async def system_stats(_: CurrentUser, session: SessionDep, monitor: MonitorDep) -> SystemStats:
    monitored = await session.scalar(
        select(func.count()).select_from(Device).where(Device.is_monitored.is_(True))
    )
    return SystemStats.model_validate(
        {
            "running": monitor.running,
            "backend": monitor.backend.name,
            "monitored_devices": monitored or 0,
            "in_flight": monitor.in_flight,
            "websocket_clients": monitor.hub.subscriber_count,
            "poller": monitor.stats.as_dict(),
            "process": monitor.process.snapshot(),
        }
    )


@router.websocket("/ws")
async def events_socket(websocket: WebSocket, token: str = Query(...)) -> None:
    """Live event stream: ``device.sample``, ``device.status``, ``alert.opened|resolved``.

    Browsers cannot set headers on WebSocket requests, so the JWT is passed as ``?token=``.
    """
    app = websocket.app
    async with app.state.session_factory() as session:
        try:
            user = await authenticate_token(session, app.state.settings, token)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    await websocket.accept()
    hub = app.state.hub
    async with hub.subscribe() as queue:
        await websocket.send_json({"type": "hello", "data": {"user": user.email}})

        async def drain_client() -> None:
            # Detect disconnects promptly; clients may send pings which we ignore.
            while True:
                await websocket.receive_text()

        reader = asyncio.create_task(drain_client())
        try:
            while not reader.done():
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {getter, reader}, timeout=25, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    await websocket.send_json(getter.result())
                else:
                    getter.cancel()
                    if not done:
                        await websocket.send_json({"type": "ping"})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await reader
