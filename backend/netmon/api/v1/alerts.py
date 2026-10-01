from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from netmon.api.deps import (
    UNPROCESSABLE,
    CurrentUser,
    MonitorDep,
    OperatorUser,
    PaginationDep,
    SessionDep,
)
from netmon.db.base import utcnow
from netmon.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    Device,
)
from netmon.schemas.alert import (
    AlertAction,
    AlertRead,
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
    AlertSummary,
)
from netmon.schemas.common import Page
from netmon.services.alerting.engine import OPEN_STATUSES, resolve_open_alerts

router = APIRouter(tags=["alerts"])


# ---------------------------------------------------------------------------- alerts
@router.get("/alerts", response_model=Page[AlertRead])
async def list_alerts(
    _: CurrentUser,
    session: SessionDep,
    paging: PaginationDep,
    status_: Annotated[list[AlertStatus] | None, Query(alias="status")] = None,
    severity: Annotated[list[AlertSeverity] | None, Query()] = None,
    device_id: int | None = None,
    open_only: bool = False,
) -> dict[str, Any]:
    page, page_size = paging
    stmt = select(Alert)
    if open_only:
        stmt = stmt.where(Alert.status.in_(OPEN_STATUSES))
    if status_:
        stmt = stmt.where(Alert.status.in_(status_))
    if severity:
        stmt = stmt.where(Alert.severity.in_(severity))
    if device_id is not None:
        stmt = stmt.where(Alert.device_id == device_id)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    items = (
        await session.scalars(
            stmt.order_by(Alert.triggered_at.desc(), Alert.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {"items": items, "total": total or 0, "page": page, "page_size": page_size}


@router.get("/alerts/summary", response_model=AlertSummary)
async def alert_summary(_: CurrentUser, session: SessionDep) -> AlertSummary:
    rows = (
        await session.execute(
            select(Alert.status, Alert.severity, func.count())
            .where(Alert.status.in_(OPEN_STATUSES))
            .group_by(Alert.status, Alert.severity)
        )
    ).all()
    by_status = {s.value: 0 for s in OPEN_STATUSES}
    by_severity = {s.value: 0 for s in AlertSeverity}
    for st, sev, n in rows:
        by_status[st.value] += n
        by_severity[sev.value] += n
    resolved_24h = await session.scalar(
        select(func.count()).where(
            Alert.status == AlertStatus.RESOLVED,
            Alert.resolved_at >= utcnow() - timedelta(hours=24),
        )
    )
    return AlertSummary(
        active=by_status["active"],
        acknowledged=by_status["acknowledged"],
        resolved_24h=resolved_24h or 0,
        by_severity=by_severity,
    )


async def _get_alert(session: SessionDep, alert_id: int) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: int, payload: AlertAction, user: OperatorUser, session: SessionDep
) -> Alert:
    alert = await _get_alert(session, alert_id)
    if alert.status != AlertStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Alert is already {alert.status.value}")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = utcnow()
    alert.acknowledged_by_id = user.id
    if payload.note:
        alert.resolution_note = payload.note
    await session.commit()
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: int,
    payload: AlertAction,
    user: OperatorUser,
    session: SessionDep,
    monitor: MonitorDep,
) -> Alert:
    alert = await _get_alert(session, alert_id)
    if alert.status == AlertStatus.RESOLVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert is already resolved")
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = utcnow()
    alert.resolution_note = payload.note or f"Resolved manually by {user.email}"
    await session.commit()
    # Restart debouncing so a still-breaching condition re-opens after `consecutive` samples.
    monitor.alerts.reset_device(alert.device_id)
    return alert


# ---------------------------------------------------------------------------- rules
@router.get("/alert-rules", response_model=list[AlertRuleRead])
async def list_rules(_: CurrentUser, session: SessionDep) -> list[AlertRule]:
    return list((await session.scalars(select(AlertRule).order_by(AlertRule.id))).all())


@router.post("/alert-rules", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(payload: AlertRuleCreate, _: OperatorUser, session: SessionDep) -> AlertRule:
    if payload.device_id is not None and await session.get(Device, payload.device_id) is None:
        raise HTTPException(UNPROCESSABLE, "Unknown device_id")
    rule = AlertRule(**payload.model_dump())
    session.add(rule)
    await session.commit()
    return rule


async def _get_rule(session: SessionDep, rule_id: int) -> AlertRule:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return rule


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleRead)
async def update_rule(
    rule_id: int, payload: AlertRuleUpdate, _: OperatorUser, session: SessionDep
) -> AlertRule:
    rule = await _get_rule(session, rule_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None or key == "description":
            setattr(rule, key, value)
    if payload.enabled is False:
        await resolve_open_alerts(session, note="Rule disabled", rule_id=rule.id)
    await session.commit()
    return rule


@router.delete("/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, _: OperatorUser, session: SessionDep) -> None:
    rule = await _get_rule(session, rule_id)
    await resolve_open_alerts(session, note="Rule deleted", rule_id=rule.id)
    await session.delete(rule)
    await session.commit()
