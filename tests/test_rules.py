"""Unit tests for app.domain.rules.evaluate_subscription."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models import Direction, QueueValue, Subscription, VehicleType
from app.domain.rules import evaluate_subscription


def _subscription(threshold: int = 1, window_end: datetime | None = None) -> Subscription:
    now = datetime.now()
    return Subscription(
        id=1,
        user_id=1,
        crossing_point_id=1,
        vehicle_type=VehicleType.CAR,
        direction=Direction.EXIT_BY,
        threshold=threshold,
        window_start=now - timedelta(hours=1),
        window_end=window_end or (now + timedelta(hours=5)),
    )


def _value(numeric_value: int | None, raw_value: str = "0") -> QueueValue:
    return QueueValue(
        id=1,
        snapshot_id=1,
        crossing_point_id=1,
        direction=Direction.EXIT_BY,
        vehicle_type=VehicleType.CAR,
        raw_value=raw_value,
        numeric_value=numeric_value,
    )


def test_matches_when_at_or_above_threshold():
    sub = _subscription(threshold=10)
    result = evaluate_subscription(sub, _value(10, "10"), datetime.now())
    assert result.matched is True
    assert result.reason == "threshold_reached"


def test_does_not_match_below_threshold():
    sub = _subscription(threshold=10)
    result = evaluate_subscription(sub, _value(5, "5"), datetime.now())
    assert result.matched is False
    assert result.reason == "below_threshold"


def test_does_not_match_missing_value():
    sub = _subscription(threshold=1)
    result = evaluate_subscription(sub, None, datetime.now())
    assert result.matched is False
    assert result.reason == "no_data_for_point"


def test_does_not_match_non_numeric_value():
    sub = _subscription(threshold=1)
    result = evaluate_subscription(sub, _value(None, "-"), datetime.now())
    assert result.matched is False
    assert result.reason == "non_numeric_value"


def test_window_expired_takes_precedence():
    sub = _subscription(threshold=1, window_end=datetime.now() - timedelta(minutes=1))
    result = evaluate_subscription(sub, _value(100, "100"), datetime.now())
    assert result.matched is False
    assert result.reason == "window_expired"
