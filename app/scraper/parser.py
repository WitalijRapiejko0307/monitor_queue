"""Parse the GPK "situation-at-the-border" HTML page into structured values.

Source page layout (confirmed via live inspection on 2026-10-21):
- `.ochered_time` holds the source timestamp, e.g. "21.10.2026 06:00".
- `<table id="car">`, `<table id="truck">`, `<table id="bus">` each hold one row
  per crossing point, columns: [name+link, exit camera icon, exit value (RB exit),
  entry camera icon, entry value (RB entry)] — only the "exit value" column is
  reliably populated for the "выезд из РБ" direction, which is what this service
  tracks for the MVP.
- A value like "(65)*" means: in the electronic-queue waiting zone, as reported by
  the zone operator (`is_electronic_queue_value=True`). A plain "0" / "12" is a
  direct camera-based reading. "-" means no data.
- A point link carrying class "text-red" means the counterpart crossing point is
  not operating.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.db.models import Direction, VehicleType

_VALUE_TABLE_IDS = {
    "car": VehicleType.CAR,
    "truck": VehicleType.TRUCK,
    "bus": VehicleType.BUS,
}

_ELECTRONIC_VALUE_RE = re.compile(r"^\((\d+)\)\*?$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+$")


class ParseError(Exception):
    """Raised when the expected page structure is not found (site layout changed)."""


@dataclass(frozen=True)
class ParsedValue:
    point_slug: str
    point_name: str
    vehicle_type: VehicleType
    direction: Direction
    raw_value: str
    numeric_value: int | None
    is_electronic_queue_value: bool
    point_not_operating: bool


@dataclass(frozen=True)
class ParsedSnapshot:
    source_time_raw: str | None
    values: list[ParsedValue]


def _parse_value_cell(raw_text: str) -> tuple[str, int | None, bool]:
    """Returns (raw_value, numeric_value_or_None, is_electronic_queue_value)."""
    text = raw_text.strip()
    if not text or text == "-":
        return text or "-", None, False

    m = _ELECTRONIC_VALUE_RE.match(text)
    if m:
        return text, int(m.group(1)), True

    if _PLAIN_NUMBER_RE.match(text):
        return text, int(text), False

    # Unknown format: keep raw text, no numeric value, not treated as electronic queue.
    return text, None, False


def parse_gpk_html(html: str, point_slugs: list[str]) -> ParsedSnapshot:
    """Parse the GPK page HTML.

    point_slugs: ordered list of slugs expected to appear as link hrefs
    `/situation-at-the-border/punkty-propuska/<slug>/`, used to attribute each
    table row to a known crossing point without relying on exact row order.
    """
    soup = BeautifulSoup(html, "lxml")

    time_el = soup.select_one(".ochered_time")
    source_time_raw = time_el.get_text(strip=True) if time_el else None

    values: list[ParsedValue] = []
    found_any_table = False

    for table_id, vehicle_type in _VALUE_TABLE_IDS.items():
        table = soup.find("table", id=table_id)
        if table is None or not isinstance(table, Tag):
            continue
        found_any_table = True

        for row in table.find_all("tr"):
            link = row.find("a", href=re.compile(r"/punkty-propuska/([^/]+)/"))
            if link is None:
                continue
            href = link.get("href", "")
            m = re.search(r"/punkty-propuska/([^/]+)/", href)
            if not m:
                continue
            slug = m.group(1)
            if slug not in point_slugs:
                continue

            point_not_operating = "text-red" in (link.get("class") or [])
            point_name = link.get_text(strip=True)

            cells = row.find_all("td")
            # Expected columns: [name, exit_camera, exit_value, entry_camera, entry_value]
            # exit_value is index 2 when present; defensively search by title attr instead.
            exit_cell = row.find("td", title=re.compile(r"выезд"))
            if exit_cell is None:
                continue
            raw_value, numeric_value, is_electronic = _parse_value_cell(
                exit_cell.get_text(strip=True)
            )

            values.append(
                ParsedValue(
                    point_slug=slug,
                    point_name=point_name,
                    vehicle_type=vehicle_type,
                    direction=Direction.EXIT_BY,
                    raw_value=raw_value,
                    numeric_value=numeric_value,
                    is_electronic_queue_value=is_electronic,
                    point_not_operating=point_not_operating,
                )
            )

    if not found_any_table:
        raise ParseError("No car/truck/bus tables found on the GPK page — layout may have changed.")

    if not values:
        raise ParseError("Tables found but no known crossing points matched any row.")

    return ParsedSnapshot(source_time_raw=source_time_raw, values=values)
