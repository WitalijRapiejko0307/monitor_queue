"""Scheduled job: read the waiting-zone API, then evaluate active subscriptions.

Runs every settings.fetch_interval_minutes (default 5).
"""

from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select

from app.bot.notifications import send_queue_notification
from app.config import settings
from app.db.models import Subscription, SubscriptionStatus
from app.db.session import get_session
from app.domain.snapshot_service import fetch_and_store_snapshot
from app.domain.subscription_processor import process_subscriptions_for_snapshot

logger = logging.getLogger(__name__)


async def run_fetch_and_evaluate(bot: Bot) -> None:
    async with get_session() as session:
        active_count_result = await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status.in_((SubscriptionStatus.ACTIVE, SubscriptionStatus.ALERTING))
            )
        )
        active_count = active_count_result.scalar_one()
        if active_count == 0:
            logger.info("Опрос пропущен: активных наблюдений нет")
            return

        snapshot = await fetch_and_store_snapshot(session)
        logger.info(
            "Snapshot #%s fetched: parse_ok=%s source_time=%s",
            snapshot.id,
            snapshot.parse_ok,
            snapshot.source_time_raw,
        )

        async def _send(telegram_id: int, subscription, result, snapshot):
            return await send_queue_notification(bot, telegram_id, subscription, result, snapshot)

        await process_subscriptions_for_snapshot(session, snapshot, _send)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        run_fetch_and_evaluate,
        trigger=CronTrigger(
            minute=f"*/{settings.fetch_interval_minutes}",
            timezone=settings.timezone,
        ),
        kwargs={"bot": bot},
        id="fetch_and_evaluate",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
