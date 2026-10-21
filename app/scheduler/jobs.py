"""Scheduled job: fetch GPK snapshot, then evaluate all active subscriptions.

Runs every 2 hours (even hours), `settings.fetch_offset_minutes` after the hour,
matching the GPK publication cadence (docs/implementation-plan.md §2).
"""

from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot.notifications import send_queue_notification
from app.config import settings
from app.db.session import get_session
from app.domain.snapshot_service import fetch_and_store_snapshot
from app.domain.subscription_processor import process_subscriptions_for_snapshot

logger = logging.getLogger(__name__)


async def run_fetch_and_evaluate(bot: Bot) -> None:
    async with get_session() as session:
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
            hour="0,2,4,6,8,10,12,14,16,18,20,22",
            minute=settings.fetch_offset_minutes,
            timezone=settings.timezone,
        ),
        kwargs={"bot": bot},
        id="fetch_and_evaluate",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
