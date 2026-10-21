"""Entrypoint: runs the Telegram bot (long polling) + APScheduler in one process.

See docs/implementation-plan.md §4 "один процесс бот+планировщик на старте".
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.admin import router as admin_router
from app.bot.middlewares import DbSessionMiddleware
from app.bot.wizard import router as wizard_router
from app.config import settings
from app.logging.setup import configure_logging
from app.scheduler.jobs import create_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()

    dispatcher.update.middleware(DbSessionMiddleware())
    # Admin router first so admin-only commands are matched before generic wizard handlers.
    dispatcher.include_router(admin_router)
    dispatcher.include_router(wizard_router)

    scheduler = create_scheduler(bot)
    scheduler.start()
    logger.info(
        "Scheduler started: fetch_and_evaluate every %s minutes",
        settings.fetch_interval_minutes,
    )

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
