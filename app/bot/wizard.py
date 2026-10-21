"""Purchase wizard: point -> vehicle type -> departure time -> threshold -> pay.

Flow matches docs/implementation-plan.md §5. Window start is "now"; window end is
derived from the departure time the user enters (today or tomorrow, whichever is
in the future). Subscription is created in PENDING_PAYMENT status and only
flips to ACTIVE after a successful Telegram payment (see payments.py).
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    CrossingPoint,
    EventType,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
    VehicleType,
)
from app.logging.events import log_event

router = Router(name="wizard")
logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

_VEHICLE_LABELS = {
    VehicleType.CAR: "Легковой",
    VehicleType.TRUCK: "Грузовой",
}


async def _get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.flush()
        await session.commit()
    return user


def _points_keyboard(points: list[CrossingPoint]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=p.name, callback_data=f"point:{p.id}")] for p in points
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _vehicle_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Легковой", callback_data="vehicle:car"),
                InlineKeyboardButton(text="Грузовой", callback_data="vehicle:truck"),
            ]
        ]
    )


def _threshold_keyboard() -> InlineKeyboardMarkup:
    options = [1, 10, 30, 50]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=str(n), callback_data=f"threshold:{n}") for n in options]
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    confirm_label = "Оплатить" if settings.payments_enabled else "Начать наблюдение"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=confirm_label, callback_data="confirm:pay"),
                InlineKeyboardButton(text="Отмена", callback_data="confirm:cancel"),
            ]
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await _get_or_create_user(session, message.from_user.id)
    intro = (
        "Этот бот присылает одно сообщение, когда на выбранном пункте пропуска "
        "собирается очередь — чтобы вы успели зарегистрироваться в зону ожидания "
        "электронной очереди перед выездом.\n\n"
    )
    if settings.payments_enabled:
        intro += (
            "Услуга платная, разовая: одна оплата = одна ночь наблюдения за одним "
            "пунктом и типом транспорта.\n\n"
            "Команда /watch — купить наблюдение."
        )
    else:
        intro += "Команда /watch — начать наблюдение."
    await message.answer(intro)


@router.message(Command("watch"))
async def cmd_watch(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    result = await session.execute(
        select(CrossingPoint).where(CrossingPoint.is_active_for_sale == True)  # noqa: E712
    )
    points = list(result.scalars().all())
    if not points:
        await message.answer("Список пунктов пропуска пока не настроен. Загляните позже.")
        return
    await state.set_state("choosing_point")
    await message.answer(
        "Выберите пункт пропуска (направление — выезд из РБ):",
        reply_markup=_points_keyboard(points),
    )


@router.callback_query(F.data.startswith("point:"))
async def on_point_chosen(callback, state: FSMContext, session: AsyncSession) -> None:
    point_id = int(callback.data.split(":", 1)[1])
    point = await session.get(CrossingPoint, point_id)
    if point is None:
        await callback.answer("Пункт не найден, попробуйте снова.", show_alert=True)
        return
    await state.update_data(point_id=point.id, point_name=point.name)
    await state.set_state("choosing_vehicle")
    await callback.message.edit_text(
        f"Пункт: {point.name}\n\nКакой у вас транспорт?",
        reply_markup=_vehicle_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("vehicle:"))
async def on_vehicle_chosen(callback, state: FSMContext) -> None:
    vehicle_raw = callback.data.split(":", 1)[1]
    vehicle_type = VehicleType.CAR if vehicle_raw == "car" else VehicleType.TRUCK
    await state.update_data(vehicle_type=vehicle_type.value)
    await state.set_state("choosing_departure_time")
    await callback.message.edit_text(
        "Во сколько планируете выезжать? Напишите время в формате ЧЧ:ММ (например, 05:00).\n"
        "Если это время уже прошло сегодня — буду считать, что это завтра утром."
    )
    await callback.answer()


@router.message(F.text.regexp(_TIME_RE.pattern))
async def on_departure_time_entered(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != "choosing_departure_time":
        return

    match = _TIME_RE.match(message.text.strip())
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        await message.answer("Похоже, время указано неверно. Формат ЧЧ:ММ, например 05:00.")
        return

    now = datetime.now(ZoneInfo(settings.timezone))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)

    await state.update_data(window_end=candidate.isoformat())
    await state.set_state("choosing_threshold")
    await message.answer(
        "С какого количества машин писать? Нажмите кнопку или отправьте своё число "
        "сообщением. Если выбрать 1 — напишу, как только очередь появится.",
        reply_markup=_threshold_keyboard(),
    )


async def _show_confirmation(message: Message, state: FSMContext, threshold: int) -> None:
    await state.update_data(threshold=threshold)
    data = await state.get_data()

    vehicle_type = VehicleType(data["vehicle_type"])
    price_minor = (
        settings.price_car_minor if vehicle_type == VehicleType.CAR else settings.price_truck_minor
    )

    await state.update_data(price_minor=price_minor)
    await state.set_state("confirming")

    summary_lines = [
        "Проверьте условия наблюдения:\n",
        f"Пункт: {data['point_name']}",
        f"Транспорт: {_VEHICLE_LABELS[vehicle_type]}",
        f"Наблюдение до: {datetime.fromisoformat(data['window_end']).strftime('%d.%m %H:%M')}",
        f"Порог: {threshold} машин",
    ]
    if settings.payments_enabled:
        price_text = f"{price_minor / 100:.2f} {settings.payment_currency}"
        summary_lines.append(f"Стоимость: {price_text}")
        summary_lines.append(
            "\nОплата разовая. Если очередь не соберётся до указанного времени — "
            "услуга считается оказанной (бот следил по данным ГПК), возврат не производится."
        )
    await message.answer("\n".join(summary_lines), reply_markup=_confirm_keyboard())


@router.callback_query(F.data.startswith("threshold:"))
async def on_threshold_chosen(callback, state: FSMContext) -> None:
    if await state.get_state() != "choosing_threshold":
        await callback.answer("Сначала выберите время выезда командой /watch.", show_alert=True)
        return
    threshold = int(callback.data.split(":", 1)[1])
    await _show_confirmation(callback.message, state, threshold)
    await callback.answer()


@router.message(F.text.regexp(r"^\d{1,4}$"))
async def on_threshold_typed(message: Message, state: FSMContext) -> None:
    if await state.get_state() != "choosing_threshold":
        return
    threshold = int(message.text.strip())
    if threshold < 1:
        await message.answer("Нужно число от 1. Отправьте количество машин или нажмите кнопку.")
        return
    await _show_confirmation(message, state, threshold)


@router.callback_query(F.data == "confirm:cancel")
async def on_confirm_cancel(callback, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено. Команда /watch — чтобы начать заново.")
    await callback.answer()


@router.callback_query(F.data == "confirm:pay")
async def on_confirm_pay(callback, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer("Запускаю наблюдение")
    data = await state.get_data()

    try:
        if not settings.payments_enabled:
            await _activate_subscription_without_payment(callback, state, session, data)
            return
        await _start_payment_flow(callback, state, session, data)
    except Exception:
        logger.exception("Failed to start a watch for telegram_id=%s", callback.from_user.id)
        await callback.message.answer(
            "Не получилось запустить наблюдение. Нажмите /watch и попробуйте ещё раз."
        )


async def _activate_subscription_without_payment(
    callback, state: FSMContext, session: AsyncSession, data: dict
) -> None:
    """Payments are disabled for now (owner decision): create the subscription
    directly in ACTIVE status, with no linked Payment row. The Payment/invoice
    code path below is kept intact so re-enabling payments later (setting
    PAYMENT_PROVIDER_TOKEN) requires no changes here.
    """
    if "vehicle_type" not in data or "point_id" not in data or "window_end" not in data:
        await callback.message.answer(
            "Шаги наблюдения сбросились. Отправьте /watch и пройдите выбор заново."
        )
        await state.clear()
        return

    vehicle_type = VehicleType(data["vehicle_type"])
    user = await _get_or_create_user(session, callback.from_user.id)

    subscription = Subscription(
        user_id=user.id,
        payment_id=None,
        crossing_point_id=data["point_id"],
        vehicle_type=vehicle_type,
        threshold=data["threshold"],
        window_start=datetime.now(ZoneInfo(settings.timezone)),
        window_end=datetime.fromisoformat(data["window_end"]),
        status=SubscriptionStatus.ACTIVE,
    )
    session.add(subscription)
    await session.flush()

    await log_event(
        session,
        EventType.SUBSCRIPTION_CREATED,
        subscription_id=subscription.id,
        telegram_id=user.telegram_id,
        payload={
            "crossing_point_id": subscription.crossing_point_id,
            "vehicle_type": subscription.vehicle_type.value,
            "threshold": subscription.threshold,
            "window_end": subscription.window_end.isoformat(),
            "payment_skipped": True,
        },
        commit=False,
    )
    await session.commit()

    await state.clear()
    await callback.message.edit_text(
        f"Наблюдение запущено.\n"
        f"Слежу за очередью до {subscription.window_end.strftime('%d.%m %H:%M')}.\n"
        f"Проверка по графику ГПК, раз в 2 часа. Напишу, как только машин станет "
        f"не меньше {subscription.threshold}."
    )


async def _start_payment_flow(
    callback, state: FSMContext, session: AsyncSession, data: dict
) -> None:
    vehicle_type = VehicleType(data["vehicle_type"])
    price_minor = data["price_minor"]

    user = await _get_or_create_user(session, callback.from_user.id)
    payment = Payment(
        user_id=user.id,
        provider="telegram_payments",
        amount_minor=price_minor,
        currency=settings.payment_currency,
        status=PaymentStatus.INVOICE_CREATED,
    )
    session.add(payment)
    await session.flush()

    subscription = Subscription(
        user_id=user.id,
        payment_id=payment.id,
        crossing_point_id=data["point_id"],
        vehicle_type=vehicle_type,
        threshold=data["threshold"],
        window_start=datetime.now(ZoneInfo(settings.timezone)),
        window_end=datetime.fromisoformat(data["window_end"]),
        status=SubscriptionStatus.PENDING_PAYMENT,
    )
    session.add(subscription)
    await session.flush()

    await log_event(
        session,
        EventType.PAYMENT_INVOICE_CREATED,
        payment_id=payment.id,
        subscription_id=subscription.id,
        telegram_id=user.telegram_id,
        payload={"amount_minor": price_minor, "currency": settings.payment_currency},
        commit=False,
    )
    await session.commit()

    await state.update_data(payment_id=payment.id, subscription_id=subscription.id)
    await state.set_state("awaiting_payment")

    await callback.message.answer_invoice(
        title="Наблюдение за очередью на границе",
        description=f"{data['point_name']}, {_VEHICLE_LABELS[vehicle_type]}, 1 ночь",
        payload=f"subscription:{subscription.id}",
        provider_token=settings.payment_provider_token,
        currency=settings.payment_currency,
        prices=[LabeledPrice(label="Наблюдение", amount=price_minor)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    subscription_id = data.get("subscription_id")
    payment_id = data.get("payment_id")
    sp = message.successful_payment

    payment = await session.get(Payment, payment_id) if payment_id else None
    subscription = await session.get(Subscription, subscription_id) if subscription_id else None

    if payment is None or subscription is None:
        await message.answer(
            "Оплата получена, но не удалось связать её с наблюдением. "
            "Напишите администратору и укажите время платежа."
        )
        return

    payment.status = PaymentStatus.SUCCEEDED
    payment.telegram_payment_charge_id = sp.telegram_payment_charge_id
    payment.raw_payload = {
        "currency": sp.currency,
        "total_amount": sp.total_amount,
        "invoice_payload": sp.invoice_payload,
        "provider_payment_charge_id": sp.provider_payment_charge_id,
    }
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.window_start = datetime.now()
    await session.flush()

    await log_event(
        session,
        EventType.PAYMENT_SUCCEEDED,
        payment_id=payment.id,
        subscription_id=subscription.id,
        telegram_id=message.from_user.id,
        payload={"telegram_payment_charge_id": sp.telegram_payment_charge_id},
        commit=False,
    )
    await log_event(
        session,
        EventType.SUBSCRIPTION_CREATED,
        subscription_id=subscription.id,
        telegram_id=message.from_user.id,
        payload={
            "crossing_point_id": subscription.crossing_point_id,
            "vehicle_type": subscription.vehicle_type.value,
            "threshold": subscription.threshold,
            "window_end": subscription.window_end.isoformat(),
        },
        commit=False,
    )
    await session.commit()

    await state.clear()
    await message.answer(
        f"Оплата получена. Слежу за очередью до "
        f"{subscription.window_end.strftime('%d.%m %H:%M')}.\n"
        f"Проверка по графику ГПК, раз в 2 часа. Напишу, как только условие выполнится."
    )
