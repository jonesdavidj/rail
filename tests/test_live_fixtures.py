"""Real-response regression checks; one test covers both complete captures."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from app.normalise import normalise_board
from app.rail_data import parse_board

FIXTURES = Path(__file__).parent / "fixtures"


def test_real_boards() -> None:
    # Only arrival, cancellation and carriage expectations, not a full-response snapshot.
    expected = {
        "sur-wat": (
            "WAT",
            [
                "19:52",
                "20:01",
                "19:57",
                "20:07",
                "20:03",
                "20:22",
                "20:31",
                "20:30",
                "20:37",
                "20:36",
            ],
            [10, 10, 12, 10, 4, 10, None, 12, 10, 12],
            "20:01",
        ),
        "wat-sur": (
            "SUR",
            [
                "19:40",
                "19:57",
                "20:05",
                "19:59",
                "20:14",
                "20:27",
                "20:35",
                "20:44",
                "20:40",
                "20:57",
            ],
            [None, 8, 10, 8, 10, 10, 10, 10, 8, 10],
            "19:23",
        ),
    }
    for name, (destination, arrivals, lengths, cancelled) in expected.items():
        body = (FIXTURES / f"{name}.json").read_bytes()
        now = datetime.fromisoformat(json.loads(body)["generatedAt"])
        board = normalise_board(parse_board(body, destination, now), destination, now)
        assert len(board.services) == 10
        assert [service.arrival.planned for service in board.services] == arrivals
        assert [service.length for service in board.services] == lengths
        assert [service.planned for service in board.services if service.status == "cancelled"] == [
            cancelled,
        ]
        for service in board.services:
            if service.planned == cancelled:
                assert "shortage of train crew" in service.reason
                assert service.arrival.cancelled
                assert "length" not in service.model_dump(exclude_none=True)
                assert "length" not in service.stops[-1].model_dump(exclude_none=True)
            else:
                assert service.status == "on_time" and service.delay_min == 0


def test_case_insensitive_feed_fields() -> None:
    body = (FIXTURES / "sur-wat.json").read_text()
    generated = datetime.fromisoformat(json.loads(body)["generatedAt"])
    now = generated + timedelta(minutes=1)
    mixed = json.loads(
        body, object_hook=lambda item: {name.swapcase(): value for name, value in item.items()}
    )
    board = normalise_board(parse_board(json.dumps(mixed).encode(), "WAT", now), "WAT", now)
    assert board.generated_at == generated
    assert board.messages[0].startswith("The gentlemen's toilets")
    service = next(service for service in board.services if service.planned == "20:01")
    assert service.status == "cancelled" and "shortage of train crew" in service.reason
    assert service.arrival.planned == "20:31" and service.arrival.cancelled


def test_missing_platform_is_tbc() -> None:
    body = (FIXTURES / "wat-sur.json").read_bytes()
    now = datetime.fromisoformat(json.loads(body)["generatedAt"])
    board = normalise_board(parse_board(body, "SUR", now), "SUR", now)
    # platformAvailable is true on the board, but this service has no platform field.
    assert board.services[0].platform == "TBC"


def test_current_minute_departure_is_not_treated_as_past() -> None:
    raw = json.loads((FIXTURES / "sur-wat.json").read_bytes())
    now = datetime.fromisoformat(raw["generatedAt"])
    service = normalise_board(raw, "WAT", now).services[0]
    assert service.planned == "19:27" and service.in_min == 0
