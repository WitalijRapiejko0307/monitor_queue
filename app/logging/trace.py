"""Formatting the full event chain for admin /trace commands."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventLog, Subscription


async def get_subscription_trace(session: AsyncSession, subscription_id: int) -> str:
    sub = await session.get(Subscription, subscription_id)
    if sub is None:
        return f"Подписка #{subscription_id} не найдена."

    events_result = await session.execute(
        select(EventLog)
        .where(EventLog.subscription_id == subscription_id)
        .order_by(EventLog.created_at.asc())
    )
    events = events_result.scalars().all()

    lines = [
        f"Подписка #{sub.id}",
        f"  пользователь (users.id): {sub.user_id}, telegram_id см. ниже по событиям",
        f"  пункт: crossing_point_id={sub.crossing_point_id}, тип={sub.vehicle_type.value}, "
        f"направление={sub.direction.value}",
        f"  порог: {sub.threshold}",
        f"  окно: {sub.window_start} .. {sub.window_end}",
        f"  статус: {sub.status.value}",
        f"  payment_id: {sub.payment_id}",
        "",
        f"События ({len(events)}):",
    ]
    for ev in events:
        lines.append(f"  [{ev.created_at}] {ev.event_type.value} payload={ev.payload}")

    if not events:
        lines.append("  (событий нет)")

    return "\n".join(lines)


async def get_user_subscriptions_summary(session: AsyncSession, telegram_id: int) -> str:
    from app.db.models import User  # local import to avoid cycle at module load time

    user_result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return f"Пользователь с telegram_id={telegram_id} не найден."

    subs_result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    subs = subs_result.scalars().all()

    lines = [f"Пользователь telegram_id={telegram_id} (users.id={user.id})", f"Подписок: {len(subs)}"]
    for sub in subs:
        lines.append(
            f"  #{sub.id} status={sub.status.value} point={sub.crossing_point_id} "
            f"vehicle={sub.vehicle_type.value} window={sub.window_start}..{sub.window_end}"
        )
    if not subs:
        lines.append("  (подписок нет)")
    return "\n".join(lines)


async def get_last_errors(session: AsyncSession, limit: int = 20) -> str:
    error_types = [
        "snapshot_fetch_parse_error",
        "snapshot_fetch_http_error",
        "notification_failed",
        "payment_failed",
    ]
    result = await session.execute(
        select(EventLog)
        .where(EventLog.event_type.in_(error_types))
        .order_by(EventLog.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    if not events:
        return "Ошибок не найдено."
    lines = [f"Последние ошибки (до {limit}):"]
    for ev in events:
        lines.append(
            f"  [{ev.created_at}] {ev.event_type.value} sub={ev.subscription_id} "
            f"payment={ev.payment_id} payload={ev.payload}"
        )
    return "\n".join(lines)
