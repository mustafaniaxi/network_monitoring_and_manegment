from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from netmon.api.deps import (
    UNPROCESSABLE,
    CurrentUser,
    MonitorDep,
    OperatorUser,
    PaginationDep,
    SessionDep,
)
from netmon.models import (
    Alert,
    CheckMethod,
    Device,
    DeviceStatus,
    DeviceType,
    Interface,
)
from netmon.schemas.alert import AlertRead
from netmon.schemas.common import Page
from netmon.schemas.device import (
    DeviceCreate,
    DeviceMetrics,
    DeviceRead,
    DeviceUpdate,
    InterfaceRead,
    MetricPoint,
)
from netmon.services import analytics
from netmon.services.alerting.engine import resolve_open_alerts

router = APIRouter(prefix="/devices", tags=["devices"])

_SECRETS = ("snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key")
_NULLABLE = ("vendor", "model", "location", "description", "mac_address",
             "poll_interval_seconds", "tcp_port", "snmp_v3_username")  # fmt: skip


async def get_device_or_404(session: SessionDep, device_id: int) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


async def _ensure_unique(
    session: SessionDep, name: str | None, ip: str | None, exclude_id: int | None = None
) -> None:
    conditions = []
    if name:
        conditions.append(func.lower(Device.name) == name.lower())
    if ip:
        conditions.append(Device.ip_address == ip)
    if not conditions:
        return
    stmt = select(Device).where(or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(Device.id != exclude_id)
    clash = await session.scalar(stmt.limit(1))
    if clash is not None:
        field = "name" if name and clash.name.lower() == name.lower() else "IP address/hostname"
        raise HTTPException(status.HTTP_409_CONFLICT, f"A device with this {field} already exists")


@router.get("", response_model=Page[DeviceRead])
async def list_devices(
    _: CurrentUser,
    session: SessionDep,
    paging: PaginationDep,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_: Annotated[DeviceStatus | None, Query(alias="status")] = None,
    device_type: DeviceType | None = None,
    sort: Annotated[
        str,
        Query(pattern=r"^-?(name|ip_address|status|device_type|last_latency_ms|last_checked_at)$"),
    ] = "name",
) -> dict[str, Any]:
    page, page_size = paging
    stmt = select(Device)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Device.name).like(like),
                func.lower(Device.ip_address).like(like),
                func.lower(func.coalesce(Device.location, "")).like(like),
                func.lower(func.coalesce(Device.vendor, "")).like(like),
            )
        )
    if status_ is not None:
        stmt = stmt.where(Device.status == status_)
    if device_type is not None:
        stmt = stmt.where(Device.device_type == device_type)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    column = getattr(Device, sort.lstrip("-"))
    order = column.desc() if sort.startswith("-") else column.asc()
    items = (
        await session.scalars(
            stmt.order_by(order, Device.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {"items": items, "total": total or 0, "page": page, "page_size": page_size}


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate, _: OperatorUser, session: SessionDep, monitor: MonitorDep
) -> Device:
    await _ensure_unique(session, payload.name, payload.ip_address)
    device = Device(**payload.model_dump(exclude_none=True))
    session.add(device)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Device already exists") from None
    monitor.invalidate()
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, _: CurrentUser, session: SessionDep) -> Device:
    return await get_device_or_404(session, device_id)


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    _: OperatorUser,
    session: SessionDep,
    monitor: MonitorDep,
) -> Device:
    device = await get_device_or_404(session, device_id)
    data = payload.model_dump(exclude_unset=True)
    await _ensure_unique(session, data.get("name"), data.get("ip_address"), exclude_id=device.id)

    for key, value in data.items():
        if key in _SECRETS:
            setattr(device, key, value or None)  # "" clears the secret
        elif value is not None or key in _NULLABLE:
            setattr(device, key, value)
    if device.check_method == CheckMethod.TCP and not device.tcp_port:
        raise HTTPException(UNPROCESSABLE, "tcp_port is required for TCP checks")
    if data.get("is_monitored") is False:
        await resolve_open_alerts(session, note="Monitoring disabled", device_id=device.id)
        device.status = DeviceStatus.UNKNOWN
        device.consecutive_failures = 0
    if "ip_address" in data or "device_type" in data:
        monitor.alerts.reset_device(device.id)
    await session.commit()
    monitor.invalidate()
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int, _: OperatorUser, session: SessionDep, monitor: MonitorDep
) -> None:
    device = await get_device_or_404(session, device_id)
    monitor.prometheus.forget_device(device.name, device.device_type.value)
    await session.delete(device)
    await session.commit()
    monitor.alerts.reset_device(device_id)
    monitor.invalidate()


@router.post("/{device_id}/check", response_model=DeviceRead, summary="Poll a device now")
async def check_device(
    device_id: int, _: OperatorUser, session: SessionDep, monitor: MonitorDep
) -> Device:
    await get_device_or_404(session, device_id)
    device = await monitor.poll_device_now(device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


@router.get("/{device_id}/metrics", response_model=DeviceMetrics)
async def device_metrics(
    device_id: int,
    _: CurrentUser,
    session: SessionDep,
    range_: Annotated[analytics.TimeRange, Query(alias="range")] = "1h",
) -> DeviceMetrics:
    await get_device_or_404(session, device_id)
    window = analytics.Window.from_range(range_)
    points = await analytics.device_series(session, device_id, window)
    return DeviceMetrics(
        device_id=device_id,
        range=range_,
        bucket_seconds=window.bucket_seconds,
        points=[MetricPoint(**p) for p in points],
    )


@router.get("/{device_id}/interfaces", response_model=list[InterfaceRead])
async def device_interfaces(device_id: int, _: CurrentUser, session: SessionDep) -> list[Interface]:
    await get_device_or_404(session, device_id)
    return list(
        (
            await session.scalars(
                select(Interface)
                .where(Interface.device_id == device_id)
                .order_by(Interface.if_index)
            )
        ).all()
    )


@router.get("/{device_id}/alerts", response_model=list[AlertRead])
async def device_alerts(
    device_id: int,
    _: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[Alert]:
    await get_device_or_404(session, device_id)
    return list(
        (
            await session.scalars(
                select(Alert)
                .where(Alert.device_id == device_id)
                .order_by(Alert.triggered_at.desc())
                .limit(limit)
            )
        ).all()
    )
