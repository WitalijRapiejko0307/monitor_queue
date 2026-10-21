"""Fetch the GPK page, parse it, persist a QueueSnapshot + QueueValues.

Also writes the corresponding event_log rows so a parse failure is always
distinguishable from a legitimate "queue = 0" reading (docs/implementation-plan.md §7).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import CrossingPoint, EventType, QueueSnapshot, QueueValue
from app.logging.events import log_event
from app.scraper.fetcher import fetch_gpk_html
from app.scraper.parser import ParseError, parse_gpk_html

logger = logging.getLogger(__name__)


async def fetch_and_store_snapshot(session: AsyncSession) -> QueueSnapshot:
    """Fetch, parse and persist one snapshot. Always returns a QueueSnapshot row,
    even on failure (parse_ok=False), so the caller can distinguish "no fresh data"
    from "fetched but queue is 0".
    """
    points_result = await session.execute(select(CrossingPoint))
    points = {cp.slug: cp for cp in points_result.scalars().all()}

    try:
        html = await fetch_gpk_html(settings.gpk_source_url)
    except Exception as exc:  # noqa: BLE001 - we want to log and persist regardless of cause
        logger.exception("Failed to fetch GPK page")
        snapshot = QueueSnapshot(parse_ok=False, source_time_raw=None)
        session.add(snapshot)
        await session.flush()
        await log_event(
            session,
            EventType.SNAPSHOT_FETCH_HTTP_ERROR,
            payload={"error": str(exc)},
        )
        return snapshot

    try:
        parsed = parse_gpk_html(html, point_slugs=list(points.keys()))
    except ParseError as exc:
        logger.error("Failed to parse GPK page: %s", exc)
        snapshot = QueueSnapshot(parse_ok=False, source_time_raw=None, raw_html_ref=None)
        session.add(snapshot)
        await session.flush()
        await log_event(
            session,
            EventType.SNAPSHOT_FETCH_PARSE_ERROR,
            payload={"error": str(exc)},
        )
        return snapshot

    snapshot = QueueSnapshot(parse_ok=True, source_time_raw=parsed.source_time_raw)
    session.add(snapshot)
    await session.flush()

    for value in parsed.values:
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
                is_electronic_queue_value=value.is_electronic_queue_value,
            )
        )

    await log_event(
        session,
        EventType.SNAPSHOT_FETCH_OK,
        payload={"source_time_raw": parsed.source_time_raw, "values_count": len(parsed.values)},
    )
    await session.commit()
    return snapshot
