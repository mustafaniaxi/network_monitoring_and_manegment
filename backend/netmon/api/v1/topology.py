from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from netmon.api.deps import UNPROCESSABLE, CurrentUser, OperatorUser, SessionDep
from netmon.models import Device, DeviceStatus, Link
from netmon.schemas.common import Message
from netmon.schemas.topology import (
    LinkCreate,
    LinkRead,
    LinkUpdate,
    NodePosition,
    Topology,
    TopologyEdge,
    TopologyNode,
)

router = APIRouter(prefix="/topology", tags=["topology"])


def edge_status(a: DeviceStatus, b: DeviceStatus) -> str:
    states = {a, b}
    if DeviceStatus.DOWN in states:
        return "down"
    if DeviceStatus.UNKNOWN in states:
        return "unknown"
    if DeviceStatus.DEGRADED in states:
        return "degraded"
    return "up"


@router.get("", response_model=Topology)
async def get_topology(_: CurrentUser, session: SessionDep) -> Topology:
    devices = {d.id: d for d in (await session.scalars(select(Device).order_by(Device.id))).all()}
    links = (await session.scalars(select(Link).order_by(Link.id))).all()
    return Topology(
        nodes=[
            TopologyNode(
                id=d.id,
                name=d.name,
                ip_address=d.ip_address,
                device_type=d.device_type,
                status=d.status,
                is_monitored=d.is_monitored,
                last_latency_ms=d.last_latency_ms,
                x=d.topology_x,
                y=d.topology_y,
            )
            for d in devices.values()
        ],
        edges=[
            TopologyEdge(
                **LinkRead.model_validate(link).model_dump(),
                status=edge_status(devices[link.source_id].status, devices[link.target_id].status),
            )
            for link in links
            if link.source_id in devices and link.target_id in devices
        ],
    )


@router.post("/links", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
async def create_link(payload: LinkCreate, _: OperatorUser, session: SessionDep) -> Link:
    for device_id in (payload.source_id, payload.target_id):
        if await session.get(Device, device_id) is None:
            raise HTTPException(UNPROCESSABLE, f"Unknown device {device_id}")
    reverse = await session.scalar(
        select(Link).where(Link.source_id == payload.target_id, Link.target_id == payload.source_id)
    )
    if reverse is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "These devices are already linked")
    link = Link(**payload.model_dump())
    session.add(link)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "These devices are already linked") from None
    return link


@router.patch("/links/{link_id}", response_model=LinkRead)
async def update_link(
    link_id: int, payload: LinkUpdate, _: OperatorUser, session: SessionDep
) -> Link:
    link = await session.get(Link, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None or key != "link_type":
            setattr(link, key, value)
    await session.commit()
    return link


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: int, _: OperatorUser, session: SessionDep) -> None:
    link = await session.get(Link, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    await session.delete(link)
    await session.commit()


@router.put("/positions", response_model=Message, summary="Save node positions of the map")
async def save_positions(
    positions: list[NodePosition], _: OperatorUser, session: SessionDep
) -> Message:
    ids = {p.device_id for p in positions}
    devices = {
        d.id: d for d in (await session.scalars(select(Device).where(Device.id.in_(ids)))).all()
    }
    for pos in positions:
        if (device := devices.get(pos.device_id)) is not None:
            device.topology_x, device.topology_y = pos.x, pos.y
    await session.commit()
    return Message(detail=f"Saved {len(devices)} positions")


@router.delete("/positions", response_model=Message, summary="Reset to automatic layout")
async def reset_positions(_: OperatorUser, session: SessionDep) -> Message:
    for device in (await session.scalars(select(Device))).all():
        device.topology_x = device.topology_y = None
    await session.commit()
    return Message(detail="Layout reset")
