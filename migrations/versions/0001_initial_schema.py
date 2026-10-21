"""Initial schema: crossing_points, queue_snapshots, queue_values, users,
payments, subscriptions, event_log.

Revision ID: 0001
Revises:
Create Date: 2026-10-21

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: types are created once below. Passing the same ENUM object
# into create_table() would emit a second CREATE TYPE and crash the deploy
# with DuplicateObjectError ("type direction already exists").
direction_enum = postgresql.ENUM("exit_by", "entry_by", name="direction", create_type=False)
vehicle_type_enum = postgresql.ENUM("car", "truck", "bus", name="vehicletype", create_type=False)
payment_status_enum = postgresql.ENUM(
    "invoice_created", "succeeded", "refunded", "failed", name="paymentstatus", create_type=False
)
subscription_status_enum = postgresql.ENUM(
    "pending_payment",
    "active",
    "fulfilled",
    "expired",
    "cancelled",
    "error",
    name="subscriptionstatus",
    create_type=False,
)
event_type_enum = postgresql.ENUM(
    "payment_invoice_created",
    "payment_succeeded",
    "payment_failed",
    "payment_refunded",
    "subscription_created",
    "subscription_cancelled",
    "snapshot_fetch_ok",
    "snapshot_fetch_parse_error",
    "snapshot_fetch_http_error",
    "rule_check",
    "window_state",
    "notification_sent",
    "notification_failed",
    name="eventtype",
    create_type=False,
)


def _create_enum(name: str, labels: tuple[str, ...]) -> None:
    values = ", ".join(f"'{label}'" for label in labels)
    op.execute(
        sa.text(
            f"""
            DO $$ BEGIN
                CREATE TYPE {name} AS ENUM ({values});
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )


def upgrade() -> None:
    _create_enum("direction", ("exit_by", "entry_by"))
    _create_enum("vehicletype", ("car", "truck", "bus"))
    _create_enum("paymentstatus", ("invoice_created", "succeeded", "refunded", "failed"))
    _create_enum(
        "subscriptionstatus",
        ("pending_payment", "active", "fulfilled", "expired", "cancelled", "error"),
    )
    _create_enum(
        "eventtype",
        (
            "payment_invoice_created",
            "payment_succeeded",
            "payment_failed",
            "payment_refunded",
            "subscription_created",
            "subscription_cancelled",
            "snapshot_fetch_ok",
            "snapshot_fetch_parse_error",
            "snapshot_fetch_http_error",
            "rule_check",
            "window_state",
            "notification_sent",
            "notification_failed",
        ),
    )

    op.create_table(
        "crossing_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("has_electronic_queue", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active_for_sale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_crossing_points_slug", "crossing_points", ["slug"])

    op.create_table(
        "queue_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source_time_raw", sa.String(32), nullable=True),
        sa.Column("parse_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_html_ref", sa.Text(), nullable=True),
    )

    op.create_table(
        "queue_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("queue_snapshots.id"), nullable=False),
        sa.Column(
            "crossing_point_id", sa.Integer(), sa.ForeignKey("crossing_points.id"), nullable=False
        ),
        sa.Column("direction", direction_enum, nullable=False),
        sa.Column("vehicle_type", vehicle_type_enum, nullable=False),
        sa.Column("raw_value", sa.String(32), nullable=False),
        sa.Column("numeric_value", sa.Integer(), nullable=True),
        sa.Column(
            "is_electronic_queue_value", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_queue_values_snapshot_id", "queue_values", ["snapshot_id"])
    op.create_index("ix_queue_values_crossing_point_id", "queue_values", ["crossing_point_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("telegram_payment_charge_id", sa.String(128), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", payment_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True, unique=True),
        sa.Column(
            "crossing_point_id", sa.Integer(), sa.ForeignKey("crossing_points.id"), nullable=False
        ),
        sa.Column("vehicle_type", vehicle_type_enum, nullable=False),
        sa.Column("direction", direction_enum, nullable=False, server_default="exit_by"),
        sa.Column("threshold", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", subscription_status_enum, nullable=False, server_default="pending_payment"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_crossing_point_id", "subscriptions", ["crossing_point_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    op.create_table(
        "event_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("event_type", event_type_enum, nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_event_log_created_at", "event_log", ["created_at"])
    op.create_index("ix_event_log_event_type", "event_log", ["event_type"])
    op.create_index("ix_event_log_subscription_id", "event_log", ["subscription_id"])
    op.create_index("ix_event_log_payment_id", "event_log", ["payment_id"])
    op.create_index("ix_event_log_telegram_id", "event_log", ["telegram_id"])


def downgrade() -> None:
    op.drop_table("event_log")
    op.drop_table("subscriptions")
    op.drop_table("payments")
    op.drop_table("users")
    op.drop_table("queue_values")
    op.drop_table("queue_snapshots")
    op.drop_table("crossing_points")

    bind = op.get_bind()
    event_type_enum.drop(bind, checkfirst=True)
    subscription_status_enum.drop(bind, checkfirst=True)
    payment_status_enum.drop(bind, checkfirst=True)
    vehicle_type_enum.drop(bind, checkfirst=True)
    direction_enum.drop(bind, checkfirst=True)
