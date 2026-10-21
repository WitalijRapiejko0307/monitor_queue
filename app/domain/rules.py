"""Subscription evaluation rule: did the queue reach the user's threshold?

See docs/implementation-plan.md §6 step 5 and the agreed rule "threshold, default 1"
(owner chose rule #2 from the 3 proposed options).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.db.models import QueueValue, Subscription


@dataclass(frozen=True)
class EvaluationResult:
    matched: bool
    reason: str
    numeric_value: int | None
    raw_value: str | None


def evaluate_subscription(
    subscription: Subscription,
    matching_value: QueueValue | None,
    now: datetime,
) -> EvaluationResult:
    """Decide whether a subscription's condition is met by this snapshot's value.

    matching_value is the QueueValue row for this subscription's crossing point,
    direction and vehicle_type within the latest snapshot (None if not found, e.g.
    parse error excluded this point, or point missing from the page).
    """
    if now > subscription.window_end:
        return EvaluationResult(
            matched=False, reason="window_expired", numeric_value=None, raw_value=None
        )

    if matching_value is None:
        return EvaluationResult(
            matched=False, reason="no_data_for_point", numeric_value=None, raw_value=None
        )

    if matching_value.numeric_value is None:
        # "-" or unparsable value: does not satisfy the condition, but is not an error either.
        return EvaluationResult(
            matched=False,
            reason="non_numeric_value",
            numeric_value=None,
            raw_value=matching_value.raw_value,
        )

    if matching_value.numeric_value >= subscription.threshold:
        return EvaluationResult(
            matched=True,
            reason="threshold_reached",
            numeric_value=matching_value.numeric_value,
            raw_value=matching_value.raw_value,
        )

    return EvaluationResult(
        matched=False,
        reason="below_threshold",
        numeric_value=matching_value.numeric_value,
        raw_value=matching_value.raw_value,
    )
