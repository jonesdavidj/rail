"""One focused calculation check for the optional Home Assistant adapter."""

from datetime import datetime

from app.config import Route
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
    assert len(result.services) == 6  # Independent of UI page size and walking-time filtering.
    assert result.next_departure is not None
    assert result.next_departure.id == "next" and result.next_departure.status == "late"
    assert result.next_departure.planned.isoformat() == "2026-10-31T00:00:00+00:00"
    assert result.next_departure.expected.isoformat() == "2026-10-31T00:05:00+00:00"
    assert result.next_departure.minutes_until_departure == 15
    assert result.next_departure.platform == "TBC" and result.next_departure.carriage_count == 4
