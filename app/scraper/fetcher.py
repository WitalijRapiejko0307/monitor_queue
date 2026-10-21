"""HTTP client for the GPK source page."""

from __future__ import annotations

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; QueueMonitorBot/1.0; "
        "+https://github.com/) telegram-queue-monitor"
    )
}

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


async def fetch_gpk_html(url: str) -> str:
    async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
