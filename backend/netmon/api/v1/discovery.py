from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from netmon.api.deps import (
    UNPROCESSABLE,
    CurrentUser,
    DiscoveryDep,
    MonitorDep,
    OperatorUser,
    SessionDep,
)
from netmon.models import Device
from netmon.schemas.common import validate_host
from netmon.schemas.discovery import (
    DiscoveredHostRead,
    ImportRequest,
    ImportResult,
    ScanJobRead,
    ScanRequest,
)
from netmon.services.discovery import DiscoveryError, DiscoveryJob

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _job_read(job: DiscoveryJob) -> ScanJobRead:
    return ScanJobRead(
        id=job.id,
        cidr=job.cidr,
        method=job.method,
        status=job.status,
        total=job.total,
        scanned=job.scanned,
        found=len(job.hosts),
        created_by=job.created_by,
        created_at=job.created_at,
        finished_at=job.finished_at,
        error=job.error,
        hosts=[DiscoveredHostRead.model_validate(h) for h in job.hosts],
    )


@router.post("/scans", response_model=ScanJobRead, status_code=status.HTTP_202_ACCEPTED)
async def start_scan(
    payload: ScanRequest, user: OperatorUser, session: SessionDep, discovery: DiscoveryDep
) -> ScanJobRead:
    known = {ip: device_id for device_id, ip in (await session.execute(
        select(Device.id, Device.ip_address))).all()}  # fmt: skip
    try:
        job = discovery.start(
            payload.cidr,
            method=payload.method,
            tcp_port=payload.tcp_port,
            snmp_community=payload.snmp_community,
            created_by=user.email,
            known=known,
        )
    except DiscoveryError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from None
    return _job_read(job)


@router.get("/scans", response_model=list[ScanJobRead])
async def list_scans(_: CurrentUser, discovery: DiscoveryDep) -> list[ScanJobRead]:
    return [_job_read(job) for job in discovery.list_jobs()]


@router.get("/scans/{job_id}", response_model=ScanJobRead)
async def get_scan(job_id: str, _: CurrentUser, discovery: DiscoveryDep) -> ScanJobRead:
    job = discovery.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    return _job_read(job)


@router.delete("/scans/{job_id}", response_model=ScanJobRead)
async def cancel_scan(job_id: str, _: OperatorUser, discovery: DiscoveryDep) -> ScanJobRead:
    job = discovery.cancel(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    return _job_read(job)


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_hosts(
    payload: ImportRequest, _: OperatorUser, session: SessionDep, monitor: MonitorDep
) -> ImportResult:
    existing_ips = set((await session.scalars(select(Device.ip_address))).all())
    existing_names = {n.lower() for n in (await session.scalars(select(Device.name))).all()}
    created: list[Device] = []
    skipped: list[str] = []
    for host in payload.hosts:
        try:
            ip = validate_host(host.ip_address)
        except ValueError:
            skipped.append(host.ip_address)
            continue
        name = host.name.strip()
        if ip in existing_ips:
            skipped.append(ip)
            continue
        if name.lower() in existing_names:
            name = f"{name} ({ip})"
        device = Device(
            name=name,
            ip_address=ip,
            device_type=host.device_type,
            snmp_enabled=payload.snmp_enabled,
            snmp_community=payload.snmp_community or None,
            tags=["discovered"],
        )
        session.add(device)
        created.append(device)
        existing_ips.add(ip)
        existing_names.add(name.lower())
    await session.commit()
    monitor.invalidate()
    return ImportResult(created=[d.id for d in created], skipped=skipped)
