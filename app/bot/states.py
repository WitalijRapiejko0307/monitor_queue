"""FSM states for the subscription-purchase wizard."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PurchaseWizard(StatesGroup):
    choosing_point = State()
    choosing_vehicle = State()
    choosing_departure_time = State()
    choosing_threshold = State()
    confirming = State()
    awaiting_payment = State()
