"""Unit tests for app.scraper.parser against a minimal HTML fixture that mirrors
the real GPK page structure (confirmed via live inspection, see
docs/implementation-plan.md §2).
"""

from __future__ import annotations

import pytest

from app.db.models import Direction, VehicleType
from app.scraper.parser import ParseError, parse_gpk_html

SAMPLE_HTML = """
<html><body>
<div class="ochered_time">21.10.2026 06:00</div>
<table id="car">
<tr>
  <td><a href="/situation-at-the-border/punkty-propuska/brest/">Брест</a></td>
  <td></td>
  <td title="Брест: выезд легковых автомобилей">(65)*</td>
  <td></td>
</tr>
<tr>
  <td><a href="/situation-at-the-border/punkty-propuska/vidzy/" class="text-red">Видзы</a></td>
  <td></td>
  <td title="Видзы: выезд легковых автомобилей">0</td>
  <td></td>
</tr>
<tr>
  <td><a href="/situation-at-the-border/punkty-propuska/kozlovichi/">Козловичи</a></td>
  <td></td>
  <td title="Козловичи: выезд легковых автомобилей">-</td>
  <td></td>
</tr>
</table>
<table id="truck">
<tr>
  <td><a href="/situation-at-the-border/punkty-propuska/brest/">Брест</a></td>
  <td></td>
  <td title="Брест: выезд грузовых автомобилей">(95)*</td>
  <td></td>
</tr>
</table>
<table id="bus">
<tr>
  <td><a href="/situation-at-the-border/punkty-propuska/brest/">Брест</a></td>
  <td></td>
  <td title="Брест: выезд автобусов">0</td>
  <td></td>
</tr>
</table>
</body></html>
"""

POINT_SLUGS = ["brest", "vidzy", "kozlovichi"]


def test_parses_source_time():
    result = parse_gpk_html(SAMPLE_HTML, POINT_SLUGS)
    assert result.source_time_raw == "21.10.2026 06:00"


def test_parses_electronic_queue_value():
    result = parse_gpk_html(SAMPLE_HTML, POINT_SLUGS)
    brest_car = next(
        v for v in result.values if v.point_slug == "brest" and v.vehicle_type == VehicleType.CAR
    )
    assert brest_car.raw_value == "(65)*"
    assert brest_car.numeric_value == 65
    assert brest_car.is_electronic_queue_value is True
    assert brest_car.direction == Direction.EXIT_BY


def test_parses_plain_number_value():
    result = parse_gpk_html(SAMPLE_HTML, POINT_SLUGS)
    vidzy_car = next(v for v in result.values if v.point_slug == "vidzy")
    assert vidzy_car.numeric_value == 0
    assert vidzy_car.is_electronic_queue_value is False
    assert vidzy_car.point_not_operating is True


def test_parses_dash_as_no_data():
    result = parse_gpk_html(SAMPLE_HTML, POINT_SLUGS)
    kozlovichi_car = next(v for v in result.values if v.point_slug == "kozlovichi")
    assert kozlovichi_car.raw_value == "-"
    assert kozlovichi_car.numeric_value is None


def test_truck_table_parsed_independently():
    result = parse_gpk_html(SAMPLE_HTML, POINT_SLUGS)
    brest_truck = next(
        v for v in result.values if v.point_slug == "brest" and v.vehicle_type == VehicleType.TRUCK
    )
    assert brest_truck.numeric_value == 95


def test_raises_on_missing_tables():
    with pytest.raises(ParseError):
        parse_gpk_html("<html><body>no tables here</body></html>", POINT_SLUGS)


def test_raises_when_no_known_points_match():
    html_with_unknown_points = (
        SAMPLE_HTML.replace("brest", "x1").replace("vidzy", "x2").replace("kozlovichi", "x3")
    )
    with pytest.raises(ParseError):
        parse_gpk_html(html_with_unknown_points, POINT_SLUGS)
