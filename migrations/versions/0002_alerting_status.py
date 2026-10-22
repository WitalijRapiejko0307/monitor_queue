"""Add alerting status and acknowledgement event.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'alerting'")
    op.execute("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'notification_acknowledged'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value without recreating the type.
    pass
