"""Read the waiting-zone API and persist a snapshot only when counts changed.

An unchanged reading is not written to queue_snapshots, queue_values, or
event_log. Failures are still recorded so a broken source stays visible.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import CrossingPoint, EventType, QueueSnapshot, QueueValue
from app.logging.events import log_event
from app.scraper.border_api import (
    BorderApiError,
    fetch_checkpoint_payload,
    parse_checkpoint_payload,
    values_signature,
)

logger = logging.getLogger(__name__)


async def _last_successful_signature(session: AsyncSession) -> tuple | None:
    result = await session.execute(
        select(QueueSnapshot)
        .where(QueueSnapshot.parse_ok.is_(True))
        .order_by(QueueSnapshot.fetched_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        return None
    values_result = await session.execute(
        select(QueueValue, CrossingPoint.slug)
        .join(CrossingPoint, CrossingPoint.id == QueueValue.crossing_point_id)
        .where(QueueValue.snapshot_id == snapshot.id)
    )
    signature = tuple(
        sorted(
            (
                slug,
                value.vehicle_type.value,
                value.direction.value,
                value.numeric_value if value.numeric_value is not None else -1,
            )
            for value, slug in values_result.all()
        )
    )
    return signature


async def fetch_and_store_snapshot(session: AsyncSession) -> QueueSnapshot:
    points_result = await session.execute(select(CrossingPoint))
    points = {cp.slug: cp for cp in points_result.scalars().all()}

    try:
        payload = await fetch_checkpoint_payload(settings.border_api_url)
        parsed = parse_checkpoint_payload(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read the waiting-zone API")
        event_type = (
            EventType.SNAPSHOT_FETCH_PARSE_ERROR
            if isinstance(exc, BorderApiError)
            else EventType.SNAPSHOT_FETCH_HTTP_ERROR
        )
        snapshot = QueueSnapshot(parse_ok=False, source_time_raw=None)
        session.add(snapshot)
        await session.flush()
        await log_event(session, event_type, payload={"error": str(exc)})
        return snapshot

    signature = values_signature(parsed)
    previous = await _last_successful_signature(session)
    if previous == signature:
        logger.info("Waiting-zone counts unchanged; snapshot and event log skipped")
        result = await session.execute(
            select(QueueSnapshot)
            .where(QueueSnapshot.parse_ok.is_(True))
            .order_by(QueueSnapshot.fetched_at.desc())
            .limit(1)
        )
        return result.scalar_one()

    source_time = datetime.now(ZoneInfo(settings.timezone)).strftime("%d.%m.%Y %H:%M")
    snapshot = QueueSnapshot(parse_ok=True, source_time_raw=source_time)
    session.add(snapshot)
    await session.flush()

    for value in parsed:
        point = points.get(value.point_slug)
        if point is None:
            continue
        session.add(
            QueueValue(
                snapshot_id=snapshot.id,
                crossing_point_id=point.id,
                direction=value.direction,
                vehicle_type=value.vehicle_type,
                raw_value=value.raw_value,
                numeric_value=value.numeric_value,
                is_electronic_queue_value=True,
            )
        )

    await log_event(
        session,
        EventType.SNAPSHOT_FETCH_OK,
        payload={"source_time_raw": source_time, "values_count": len(parsed)},
    )
    await session.commit()
    return snapshot
