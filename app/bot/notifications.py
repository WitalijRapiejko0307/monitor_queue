"""Sending the "queue has formed" notification to the user."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import QueueSnapshot, Subscription
from app.domain.rules import EvaluationResult

logger = logging.getLogger(__name__)


def _ack_keyboard(subscription: Subscription) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Принято", callback_data=f"ack:{subscription.id}")]
        ]
    )


def build_notification_text(
    subscription: Subscription,
    result: EvaluationResult,
    snapshot: QueueSnapshot,
    *,
    reminder: bool = False,
) -> str:
    direction_text = "выезд из РБ" if subscription.direction.value == "exit_by" else "въезд в РБ"
    vehicle_text = {"car": "легковой", "truck": "грузовой", "bus": "автобус"}[
        subscription.vehicle_type.value
    ]
    count = result.numeric_value if result.numeric_value is not None else "нет свежих данных"
    if result.reason == "window_expired":
        return (
            f"Время выезда наступило, напоминания остановлены.\n"
            f"Направление: {direction_text}, тип: {vehicle_text}."
        )
    title = "Напоминание: очередь уже собралась, «Принято» ещё не нажато." if reminder else "🚦 Очередь собралась!"
    electronic_note = (
        "\n\nЧисло из зоны ожидания электронной очереди. "
        "Чтобы занять место, зарегистрируйтесь у оператора зоны.\n"
        "Нажмите «Принято», чтобы остановить напоминания."
    )
    return (
        f"{title}\n\n"
        f"Направление: {direction_text}\n"
        f"Тип транспорта: {vehicle_text}\n"
        f"Машин в очереди: {count} (порог был {subscription.threshold})\n"
        f"Время проверки: {snapshot.source_time_raw or 'неизвестно'}"
        f"{electronic_note}"
    )


def build_window_expired_text(subscription: Subscription) -> str:
    direction_text = "выезд из РБ" if subscription.direction.value == "exit_by" else "въезд в РБ"
    vehicle_text = {"car": "легковой", "truck": "грузовой", "bus": "автобус"}[
        subscription.vehicle_type.value
    ]
    return (
        f"По данным зоны ожидания очередь не собралась до указанного времени выезда.\n"
        f"Направление: {direction_text}, тип: {vehicle_text}, порог: {subscription.threshold}.\n"
        f"Наблюдение завершено, услуга оказана."
    )


async def send_queue_notification(
    bot: Bot,
    telegram_id: int,
    subscription: Subscription,
    result: EvaluationResult,
    snapshot: QueueSnapshot,
) -> tuple[bool, str | None]:
    reminder = subscription.status.value == "alerting" and result.reason != "window_expired"
    text = build_notification_text(subscription, result, snapshot, reminder=reminder)
    markup = None if result.reason == "window_expired" else _ack_keyboard(subscription)
    try:
        await bot.send_message(chat_id=telegram_id, text=text, reply_markup=markup)
        return True, None
    except TelegramAPIError as exc:
        logger.exception("Failed to send notification to %s", telegram_id)
        return False, str(exc)


async def send_window_expired_notice(bot: Bot, telegram_id: int, subscription: Subscription) -> None:
    try:
        await bot.send_message(chat_id=telegram_id, text=build_window_expired_text(subscription))
    except TelegramAPIError:
        logger.exception("Failed to send window-expired notice to %s", telegram_id)
