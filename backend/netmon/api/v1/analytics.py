"""Dashboard KPIs, historical series and reports."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from netmon.api.deps import CurrentUser, SessionDep
from netmon.schemas.analytics import (
    AvailabilityRow,
    Bottlenecks,
    DashboardSummary,
    DegradationRow,
    DetectionReport,
    NetworkPoint,
    NetworkSeries,
    TrafficHeatmap,
)
from netmon.services import analytics
from netmon.services.analytics import TimeRange, Window

router = APIRouter(tags=["analytics"])

RangeQuery = Annotated[TimeRange, Query(alias="range")]


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    return await analytics.dashboard_summary(session)


@router.get("/dashboard/timeseries", response_model=NetworkSeries)
async def dashboard_timeseries(
    _: CurrentUser, session: SessionDep, range_: RangeQuery = "24h"
) -> NetworkSeries:
    window = Window.from_range(range_)
    points = await analytics.network_series(session, window)
    return NetworkSeries(
        range=range_,
        bucket_seconds=window.bucket_seconds,
        points=[NetworkPoint(**p) for p in points],
    )


@router.get("/reports/availability", response_model=list[AvailabilityRow])
async def availability(
    _: CurrentUser, session: SessionDep, range_: RangeQuery = "7d"
) -> list[dict[str, Any]]:
    return await analytics.availability_report(session, Window.from_range(range_))


def _csv_stream(header: list[str], rows: AsyncIterator[list[Any]]) -> AsyncIterator[str]:
    async def generate() -> AsyncIterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        async for row in rows:
            writer.writerow(row)
            if buffer.tell() > 64_000:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()

    return generate()


@router.get("/reports/availability.csv", response_class=StreamingResponse)
async def availability_csv(
    _: CurrentUser, session: SessionDep, range_: RangeQuery = "7d"
) -> StreamingResponse:
    report = await analytics.availability_report(session, Window.from_range(range_))
    header = list(AvailabilityRow.model_fields)

    async def rows() -> AsyncIterator[list[Any]]:
        for row in report:
            yield [row[k] for k in header]

    return StreamingResponse(
        _csv_stream(header, rows()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="availability-{range_}.csv"'},
    )


@router.get("/reports/top-failing", response_model=list[AvailabilityRow])
async def top_failing(
    _: CurrentUser,
    session: SessionDep,
    range_: RangeQuery = "7d",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[dict[str, Any]]:
    return await analytics.top_failing(session, Window.from_range(range_), limit)


@router.get("/reports/traffic-heatmap", response_model=TrafficHeatmap)
async def traffic_heatmap(
    _: CurrentUser,
    session: SessionDep,
    range_: RangeQuery = "7d",
    tz_offset_minutes: Annotated[int, Query(ge=-840, le=840)] = 0,
) -> dict[str, Any]:
    return await analytics.traffic_heatmap(session, Window.from_range(range_), tz_offset_minutes)


@router.get("/reports/bottlenecks", response_model=Bottlenecks)
async def bottlenecks(
    _: CurrentUser,
    session: SessionDep,
    range_: RangeQuery = "24h",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    return await analytics.bottlenecks(session, Window.from_range(range_), limit)


@router.get("/reports/degradation", response_model=list[DegradationRow])
async def degradation(
    _: CurrentUser, session: SessionDep, range_: RangeQuery = "7d"
) -> list[dict[str, Any]]:
    return await analytics.degradation(session, Window.from_range(range_))


@router.get("/reports/detection", response_model=DetectionReport)
async def detection(
    _: CurrentUser, session: SessionDep, range_: RangeQuery = "7d"
) -> dict[str, Any]:
    return await analytics.detection_report(session, Window.from_range(range_))


@router.get("/reports/samples.csv", response_class=StreamingResponse)
async def samples_csv(
    _: CurrentUser,
    session: SessionDep,
    range_: RangeQuery = "24h",
    device_id: int | None = None,
) -> StreamingResponse:
    """Raw measurements for offline analysis (spreadsheets, pandas, R)."""
    window = Window.from_range(range_)
    suffix = f"-device{device_id}" if device_id else ""
    return StreamingResponse(
        _csv_stream(analytics.SAMPLE_COLUMNS, analytics.iter_samples(session, window, device_id)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="samples-{range_}{suffix}.csv"'},
    )
