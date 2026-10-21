"""Live electronic-queue counts from the waiting-zone monitor.

The page https://mon.declarant.by/#/zone loads JSON from
https://belarusborder.by/info/checkpoint. Counts are cars and trucks already
registered in the waiting zone, which is the number the user needs in order
to decide whether to register.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.db.models import Direction, VehicleType

NAME_TO_SLUG = {
    "Бенякони": "benekainys",
    "Берестовица": "berestovitsa",
    "Брест": "brest",
    "Брузги": "bruzgi",
    "Григоровщина": "grigorov",
    "Каменный Лог": "stone_log",
    "Козловичи": "kozlovichi",
    "Урбаны": "urbana",
    "Котловка": "kotlovka",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QueueMonitorBot/1.0)",
    "Accept": "application/json",
}
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class BorderApiError(Exception):
    """The checkpoint API did not return a usable payload."""


@dataclass(frozen=True)
class BorderValue:
    point_slug: str
    vehicle_type: VehicleType
    direction: Direction
    raw_value: str
    numeric_value: int
    is_electronic_queue_value: bool = True


async def fetch_checkpoint_payload(url: str) -> dict:
    async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), list):
        raise BorderApiError("Checkpoint API response has no result list")
    return payload


def parse_checkpoint_payload(payload: dict) -> list[BorderValue]:
    values: list[BorderValue] = []
    for row in payload["result"]:
        slug = NAME_TO_SLUG.get(str(row.get("name", "")).strip())
        if slug is None:
            continue
        for vehicle_type, field in (
            (VehicleType.CAR, "countCar"),
            (VehicleType.TRUCK, "countTruck"),
            (VehicleType.BUS, "countBus"),
        ):
            if field not in row or row[field] is None:
                continue
            number = int(row[field])
            values.append(
                BorderValue(
                    point_slug=slug,
                    vehicle_type=vehicle_type,
                    direction=Direction.EXIT_BY,
                    raw_value=str(number),
                    numeric_value=number,
                )
            )
    if not values:
        raise BorderApiError("Checkpoint API returned no known waiting zones")
    return values


def values_signature(values: list[BorderValue]) -> tuple[tuple[str, str, str, int], ...]:
    return tuple(
        sorted(
            (item.point_slug, item.vehicle_type.value, item.direction.value, item.numeric_value)
            for item in values
        )
    )
