"""Append-only business event log.

Every call inserts a new row into event_log; existing rows are never updated or
deleted. This is the audit trail used by admin /trace* commands to reconstruct
what happened for a subscription, payment, or user.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventLog, EventType


async def log_event(
    session: AsyncSession,
    event_type: EventType,
    *,
    subscription_id: int | None = None,
    payment_id: int | None = None,
    telegram_id: int | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> EventLog:
    row = EventLog(
        event_type=event_type,
        subscription_id=subscription_id,
        payment_id=payment_id,
        telegram_id=telegram_id,
        payload=payload or {},
    )
    session.add(row)
    await session.flush()
    if commit:
        await session.commit()
    return row
