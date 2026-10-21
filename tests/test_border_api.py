from app.db.models import VehicleType
from app.scraper.border_api import BorderApiError, parse_checkpoint_payload, values_signature
import pytest


PAYLOAD = {
    "result": [
        {"name": "Брест", "countCar": 90, "countTruck": 0, "countBus": 0},
        {"name": "Неизвестный пункт", "countCar": 5, "countTruck": 5, "countBus": 0},
    ]
}


def test_parses_known_zone_counts():
    values = parse_checkpoint_payload(PAYLOAD)
    brest_car = next(v for v in values if v.point_slug == "brest" and v.vehicle_type == VehicleType.CAR)
    assert brest_car.numeric_value == 90
    assert brest_car.is_electronic_queue_value is True


def test_ignores_unknown_zone_names():
    values = parse_checkpoint_payload(PAYLOAD)
    assert all(v.point_slug == "brest" for v in values)


def test_signature_ignores_order():
    values = parse_checkpoint_payload(PAYLOAD)
    assert values_signature(values) == values_signature(list(reversed(values)))


def test_empty_known_zones_raise():
    with pytest.raises(BorderApiError):
        parse_checkpoint_payload({"result": [{"name": "Другой", "countCar": 1}]})
