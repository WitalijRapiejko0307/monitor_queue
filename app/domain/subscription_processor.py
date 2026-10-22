"""After a snapshot is stored, evaluate every active subscription against it
and send notifications where the condition is met.

Writes window_state + rule_check events for every subscription on every run,
so /trace shows exactly what the algorithm saw at each check (docs/implementation-plan.md §6).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    EventLog,
    EventType,
    QueueSnapshot,
    QueueValue,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.domain.rules import evaluate_subscription
from app.logging.events import log_event

logger = logging.getLogger(__name__)

# async def(telegram_id: int, subscription, result, snapshot) -> (sent_ok, error_message)
NotificationSender = Callable[..., Awaitable[tuple[bool, str | None]]]


async def process_subscriptions_for_snapshot(
    session: AsyncSession,
    snapshot: QueueSnapshot,
    send_notification: NotificationSender,
) -> None:
    now = datetime.now(timezone.utc)

    active_result = await session.execute(
        select(Subscription).where(
            Subscription.status.in_((SubscriptionStatus.ACTIVE, SubscriptionStatus.ALERTING))
        )
    )
    active_subscriptions = active_result.scalars().all()

    for subscription in active_subscriptions:
        if now > subscription.window_end:
            await log_event(
                session,
                EventType.WINDOW_STATE,
                subscription_id=subscription.id,
                payload={"state": "window_expired", "checked_at": now.isoformat()},
                commit=False,
            )
            if subscription.status == SubscriptionStatus.ALERTING:
                user = await session.get(User, subscription.user_id)
                if user is not None:
                    await send_notification(
                        telegram_id=user.telegram_id,
                        subscription=subscription,
                        result=evaluate_subscription(subscription, None, now),
                        snapshot=snapshot,
                    )
            subscription.status = SubscriptionStatus.EXPIRED
            await session.flush()
            continue

        if not await _same_as_last_event(
            session,
            subscription.id,
            EventType.WINDOW_STATE,
            {"state": "window_open"},
        ):
            await log_event(
                session,
                EventType.WINDOW_STATE,
                subscription_id=subscription.id,
                payload={"state": "window_open", "checked_at": now.isoformat()},
                commit=False,
            )

        matching_value: QueueValue | None = None
        if snapshot.parse_ok:
            value_result = await session.execute(
                select(QueueValue).where(
                    QueueValue.snapshot_id == snapshot.id,
                    QueueValue.crossing_point_id == subscription.crossing_point_id,
                    QueueValue.direction == subscription.direction,
                    QueueValue.vehicle_type == subscription.vehicle_type,
                )
            )
            matching_value = value_result.scalar_one_or_none()

        result = evaluate_subscription(subscription, matching_value, now)

        rule_payload = {
            "snapshot_id": snapshot.id,
            "snapshot_parse_ok": snapshot.parse_ok,
            "threshold": subscription.threshold,
            "numeric_value": result.numeric_value,
            "raw_value": result.raw_value,
            "matched": result.matched,
            "reason": result.reason,
        }
        if not await _same_as_last_event(
            session,
            subscription.id,
            EventType.RULE_CHECK,
            {
                "numeric_value": result.numeric_value,
                "raw_value": result.raw_value,
                "matched": result.matched,
                "reason": result.reason,
            },
        ):
            await log_event(
                session,
                EventType.RULE_CHECK,
                subscription_id=subscription.id,
                payload=rule_payload,
                commit=False,
            )

        should_notify = result.matched or subscription.status == SubscriptionStatus.ALERTING
        if should_notify:
            user = await session.get(User, subscription.user_id)
            if user is not None:
                sent_ok, send_error = await send_notification(
                    telegram_id=user.telegram_id,
                    subscription=subscription,
                    result=result,
                    snapshot=snapshot,
                )
                await log_event(
                    session,
                    EventType.NOTIFICATION_SENT if sent_ok else EventType.NOTIFICATION_FAILED,
                    subscription_id=subscription.id,
                    telegram_id=user.telegram_id,
                    payload={
                        "numeric_value": result.numeric_value,
                        "raw_value": result.raw_value,
                        "error": send_error,
                        "reminder": subscription.status == SubscriptionStatus.ALERTING,
                    },
                    commit=False,
                )
                if sent_ok and subscription.status == SubscriptionStatus.ACTIVE:
                    subscription.status = SubscriptionStatus.ALERTING
                    await session.flush()

    await session.commit()


async def _same_as_last_event(
    session: AsyncSession,
    subscription_id: int,
    event_type: EventType,
    expected: dict,
) -> bool:
    """True when the latest event of this type already recorded the same facts.

    Repeated 5-minute checks then stay out of event_log until the queue number
    or the decision changes.
    """
    result = await session.execute(
        select(EventLog)
        .where(
            EventLog.subscription_id == subscription_id,
            EventLog.event_type == event_type,
        )
        .order_by(EventLog.created_at.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last is None or not last.payload:
        return False
    return all(last.payload.get(key) == value for key, value in expected.items())
