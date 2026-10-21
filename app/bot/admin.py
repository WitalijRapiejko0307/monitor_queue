"""Admin-only commands for investigating disputes and errors.

Access is restricted to telegram_id values listed in settings.admin_telegram_ids
(docs/implementation-plan.md §5/§8: "Админ-команды недоступны никому кроме
указанного telegram_id").
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import QueueSnapshot, Subscription, SubscriptionStatus
from app.logging.trace import get_last_errors, get_subscription_trace, get_user_subscriptions_summary

router = Router(name="admin")


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_telegram_ids


@router.message(Command("trace"))
async def cmd_trace(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /trace <subscription_id>")
        return
    text = await get_subscription_trace(session, int(command.args.strip()))
    await message.answer(text)


@router.message(Command("trace_user"))
async def cmd_trace_user(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /trace_user <telegram_id>")
        return
    text = await get_user_subscriptions_summary(session, int(command.args.strip()))
    await message.answer(text)


@router.message(Command("last_errors"))
async def cmd_last_errors(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    limit = 20
    if command.args and command.args.strip().isdigit():
        limit = int(command.args.strip())
    text = await get_last_errors(session, limit=limit)
    await message.answer(text)


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    last_snapshot_result = await session.execute(
        select(QueueSnapshot).order_by(QueueSnapshot.fetched_at.desc()).limit(1)
    )
    last_snapshot = last_snapshot_result.scalar_one_or_none()

    active_count_result = await session.execute(
        select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE
        )
    )
    active_count = active_count_result.scalar_one()

    if last_snapshot is None:
        snapshot_line = "Снапшотов ещё не было."
    else:
        snapshot_line = (
            f"Последний снапшот: #{last_snapshot.id}, fetched_at={last_snapshot.fetched_at}, "
            f"parse_ok={last_snapshot.parse_ok}, source_time={last_snapshot.source_time_raw}"
        )

    await message.answer(
        f"{snapshot_line}\nАктивных наблюдений: {active_count}\n"
        f"Платежи включены: {settings.payments_enabled}"
    )


@router.message(Command("force_fetch"))
async def cmd_force_fetch(message: Message, session: AsyncSession, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return

    from app.bot.notifications import send_queue_notification
    from app.domain.snapshot_service import fetch_and_store_snapshot
    from app.domain.subscription_processor import process_subscriptions_for_snapshot

    await message.answer("Запускаю внеочередной опрос ГПК...")
    try:
        snapshot = await fetch_and_store_snapshot(session)

        async def _send(telegram_id: int, subscription, result, snapshot):
            return await send_queue_notification(bot, telegram_id, subscription, result, snapshot)

        await process_subscriptions_for_snapshot(session, snapshot, _send)
    except Exception as exc:
        await message.answer(f"Опрос не завершился: {exc}")
        raise

    await message.answer(
        f"Готово. Снапшот #{snapshot.id}, parse_ok={snapshot.parse_ok}, "
        f"source_time={snapshot.source_time_raw}. "
        "Если условие наблюдения выполнилось, сообщение ушло в этот же чат."
    )
