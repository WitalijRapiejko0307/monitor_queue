"""SQLAlchemy ORM models.

Schema follows docs/implementation-plan.md section 3 ("Модель данных"):
crossing_points, queue_snapshots, queue_values, users, payments, subscriptions, event_log.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _pg_enum(enum_cls: type[enum.Enum], pg_name: str) -> Enum:
    """Store enum values ('car'), not member names ('CAR'). Postgres types were
    created with the lowercase values from the migration.
    """
    return Enum(
        enum_cls,
        name=pg_name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
    )


class Direction(str, enum.Enum):
    EXIT_BY = "exit_by"  # выезд из РБ
    ENTRY_BY = "entry_by"  # въезд в РБ


class VehicleType(str, enum.Enum):
    CAR = "car"
    TRUCK = "truck"
    BUS = "bus"


class PaymentStatus(str, enum.Enum):
    INVOICE_CREATED = "invoice_created"
    SUCCEEDED = "succeeded"
    REFUNDED = "refunded"
    FAILED = "failed"


class SubscriptionStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    ACTIVE = "active"
    ALERTING = "alerting"
    FULFILLED = "fulfilled"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    ERROR = "error"


class EventType(str, enum.Enum):
    PAYMENT_INVOICE_CREATED = "payment_invoice_created"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SNAPSHOT_FETCH_OK = "snapshot_fetch_ok"
    SNAPSHOT_FETCH_PARSE_ERROR = "snapshot_fetch_parse_error"
    SNAPSHOT_FETCH_HTTP_ERROR = "snapshot_fetch_http_error"
    RULE_CHECK = "rule_check"
    WINDOW_STATE = "window_state"
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_FAILED = "notification_failed"
    NOTIFICATION_ACKNOWLEDGED = "notification_acknowledged"


class CrossingPoint(Base):
    __tablename__ = "crossing_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    has_electronic_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active_for_sale: Mapped[bool] = mapped_column(Boolean, default=False)

    queue_values: Mapped[list["QueueValue"]] = relationship(back_populates="crossing_point")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="crossing_point")


class QueueSnapshot(Base):
    __tablename__ = "queue_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_time_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parse_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_html_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    values: Mapped[list["QueueValue"]] = relationship(back_populates="snapshot")


class QueueValue(Base):
    __tablename__ = "queue_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("queue_snapshots.id"), index=True)
    crossing_point_id: Mapped[int] = mapped_column(ForeignKey("crossing_points.id"), index=True)
    direction: Mapped[Direction] = mapped_column(_pg_enum(Direction, "direction"))
    vehicle_type: Mapped[VehicleType] = mapped_column(_pg_enum(VehicleType, "vehicletype"))
    raw_value: Mapped[str] = mapped_column(String(32))
    numeric_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_electronic_queue_value: Mapped[bool] = mapped_column(Boolean, default=False)

    snapshot: Mapped[QueueSnapshot] = relationship(back_populates="values")
    crossing_point: Mapped[CrossingPoint] = relationship(back_populates="queue_values")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[PaymentStatus] = mapped_column(_pg_enum(PaymentStatus, "paymentstatus"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped[User] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="payment")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True, unique=True
    )
    crossing_point_id: Mapped[int] = mapped_column(ForeignKey("crossing_points.id"), index=True)
    vehicle_type: Mapped[VehicleType] = mapped_column(_pg_enum(VehicleType, "vehicletype"))
    direction: Mapped[Direction] = mapped_column(
        _pg_enum(Direction, "direction"), default=Direction.EXIT_BY
    )
    threshold: Mapped[int] = mapped_column(Integer, default=1)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[SubscriptionStatus] = mapped_column(
        _pg_enum(SubscriptionStatus, "subscriptionstatus"),
        default=SubscriptionStatus.PENDING_PAYMENT,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    payment: Mapped[Payment | None] = relationship(back_populates="subscription")
    crossing_point: Mapped[CrossingPoint] = relationship(back_populates="subscriptions")


class EventLog(Base):
    """Append-only audit log. Never update or delete rows, only insert."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    event_type: Mapped[EventType] = mapped_column(_pg_enum(EventType, "eventtype"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True, index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True, index=True
    )
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
