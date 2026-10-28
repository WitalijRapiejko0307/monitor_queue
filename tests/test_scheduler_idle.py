"""Tests for run_fetch_and_evaluate when there are no active subscriptions."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler.jobs import run_fetch_and_evaluate


def _patch_session(active_count: int):
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = active_count
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def fake_get_session():
        yield mock_session

    return fake_get_session, mock_session


@pytest.mark.asyncio
async def test_skips_fetch_when_no_active_or_alerting_subscriptions():
    fake_get_session, mock_session = _patch_session(0)

    with (
        patch("app.scheduler.jobs.get_session", fake_get_session),
        patch("app.scheduler.jobs.fetch_and_store_snapshot", new_callable=AsyncMock) as mock_fetch,
        patch(
            "app.scheduler.jobs.process_subscriptions_for_snapshot",
            new_callable=AsyncMock,
        ) as mock_process,
    ):
        await run_fetch_and_evaluate(bot=object())

    mock_session.execute.assert_awaited_once()
    mock_fetch.assert_not_awaited()
    mock_process.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetches_snapshot_once_when_subscriptions_exist():
    fake_get_session, mock_session = _patch_session(2)
    mock_snapshot = MagicMock()
    mock_snapshot.id = 7
    mock_snapshot.parse_ok = True
    mock_snapshot.source_time_raw = "10:00"

    with (
        patch("app.scheduler.jobs.get_session", fake_get_session),
        patch(
            "app.scheduler.jobs.fetch_and_store_snapshot",
            new_callable=AsyncMock,
            return_value=mock_snapshot,
        ) as mock_fetch,
        patch(
            "app.scheduler.jobs.process_subscriptions_for_snapshot",
            new_callable=AsyncMock,
        ) as mock_process,
    ):
        await run_fetch_and_evaluate(bot=object())

    mock_fetch.assert_awaited_once_with(mock_session)
    mock_process.assert_awaited_once()
    process_args, _process_kwargs = mock_process.await_args
    assert process_args[0] is mock_session
    assert process_args[1] is mock_snapshot
    assert callable(process_args[2])
