"""One focused calculation check for the optional Home Assistant adapter."""

import json
from datetime import datetime
from pathlib import Path

from app.config import Route, defaults
from app.integrations.home_assistant import summarise
from app.normalise import LONDON, normalise_board


def test_summary_counts_window_and_selects_usable_departure() -> None:
    now = datetime(2026, 10, 30, 23, 50, tzinfo=LONDON)
    route = Route(
        id="out",
        label="Home",
        origin="SUR",
        destination="WAT",
        min_departure_minutes=8,
        page_size=1,
    )
    raw = {
        "trainServices": [
            {"serviceID": "too-soon", "std": "23:52", "etd": "On time"},
            {"serviceID": "cancelled", "std": "23:55", "etd": "Cancelled"},
            {"serviceID": "next", "std": "00:00", "etd": "00:05", "length": 4},
            {"serviceID": "call-cancelled", "std": "00:10", "filterLocationCancelled": True},
            {"serviceID": "delayed", "std": "00:20", "etd": "Delayed"},
            {"serviceID": "later", "std": "00:30", "etd": "On time"},
            {"serviceID": "outside", "std": "01:50", "etd": "Cancelled"},
        ]
    }
    result = summarise(normalise_board(raw, "WAT", now).services, route, now)
    assert (result.cancelled_count, result.delayed_count) == (2, 2)
    assert len(result.services) == 4  # Walking allowance applies to rows, not disruption totals.
    assert result.next_departure is not None
    assert result.next_departure.id == "next" and result.next_departure.status == "late"
    assert result.next_departure.planned.isoformat() == "2026-10-31T00:00:00+00:00"
    assert result.next_departure.expected.isoformat() == "2026-10-31T00:05:00+00:00"
    assert result.next_departure.minutes_until_departure == 15
    assert result.next_departure.platform == "TBC" and result.next_departure.carriage_count == 4


def test_summary_service_shape_limit_cancellation_and_fast() -> None:
    raw = json.loads((Path(__file__).parent / "fixtures" / "wat-sur.json").read_bytes())
    now = datetime.fromisoformat(raw["generatedAt"]).replace(minute=20)
    route = defaults().routes[1].model_copy(update={"min_departure_minutes": 2})
    result = summarise(normalise_board(raw, "SUR", now).services, route, now, n=7)
    rows = result.model_dump(mode="json", exclude_unset=True)["services"]
    assert len(rows) == 7
    assert set(rows[0]) == {
        "id",
        "planned",
        "status",
        "expected",
        "delay_minutes",
        "platform",
        "carriage_count",
        "destination",
        "arrival_planned",
        "arrival_expected",
        "journey_minutes",
        "stop_count",
        "fast",
    }
    assert rows[0]["status"] == "cancelled" and not rows[0]["fast"]
    assert rows[0]["platform"] is None and rows[0]["carriage_count"] is None
    assert rows[1]["destination"] == "Guildford via Cobham"
    assert rows[1]["delay_minutes"] == 0 and rows[1]["expected"] == rows[1]["planned"]
    assert rows[1]["arrival_planned"].endswith("Z") and rows[1]["arrival_expected"].endswith("Z")
    assert rows[3]["fast"] and rows[3]["stop_count"] == 0
    assert len(result.model_dump_json().encode()) < 4096


def test_summary_stops_are_opt_in_and_end_at_destination() -> None:
    raw = json.loads((Path(__file__).parent / "fixtures" / "wat-sur.json").read_bytes())
    now = datetime.fromisoformat(raw["generatedAt"]).replace(minute=20)
    route = defaults().routes[1].model_copy(update={"min_departure_minutes": 2})
    services = normalise_board(raw, "SUR", now).services
    plain = summarise(services, route, now, n=7).model_dump(mode="json", exclude_unset=True)
    rows = summarise(services, route, now, n=7, with_stops=True).model_dump(
        mode="json", exclude_unset=True
    )["services"]
    assert all("stops" not in row for row in plain["services"])
    stops = rows[1]["stops"]
    assert set(stops[0]) == {"name", "crs", "planned", "expected", "cancelled"}
    assert stops[-1]["crs"] == route.destination
