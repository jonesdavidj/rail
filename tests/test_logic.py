"""Focused tests for silent data/config/paging mistakes; no exhaustive matrices."""

import copy
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Route, RouteConfig, RouteWrite, defaults, load_config
from app.normalise import Raw, normalise_board
from app.paging import cursor_offset, page_board, read_cursor
from app.providers import DemoProvider
from app.routes import RouteStore


@pytest.fixture
def raw() -> Raw:
    # Minimal synthetic data only for estimates/midnight/group branches absent in captures.
    return {
        "trainServices": [
            {
                "serviceID": "example",
                "std": "18:05",
                "etd": "18:12",
                "subsequentCallingPoints": [
                    {
                        "callingPoint": [
                            {"crs": "CLJ", "st": "18:19", "et": "18:26"},
                            {"crs": "WAT", "st": "18:29", "et": "18:36"},
                        ]
                    }
                ],
            }
        ]
    }


def test_expected_departure_delay(raw: Raw, now: datetime) -> None:
    service = normalise_board(raw, "WAT", now).services[0]
    assert (service.status, service.delay_min, service.expected) == ("late", 7, "18:12")


def test_unknown_and_delayed_estimates(raw: Raw, now: datetime) -> None:
    raw["trainServices"][0].update(etd="No report")
    service = normalise_board(raw, "WAT", now).services[0]
    assert service.status == "unknown" and service.expected is None
    raw["trainServices"][0]["etd"] = "Delayed"
    assert normalise_board(raw, "WAT", now).services[0].status == "delayed"


def test_destination_group_and_partial_cancellation(raw: Raw, now: datetime) -> None:
    groups = raw["trainServices"][0]["subsequentCallingPoints"]
    groups[0]["callingPoint"][-1].update(isCancelled=True, cancelReason="Stop cancelled")
    wrong = copy.deepcopy(groups[0])
    wrong["serviceChangeRequired"] = True
    wrong["callingPoint"][-1]["st"] = "19:00"
    groups.insert(0, wrong)
    service = normalise_board(raw, "WAT", now).services[0]
    assert service.status == "part_cancelled" and service.reason == "Stop cancelled"
    assert service.arrival and service.arrival.planned == "18:29"


def test_midnight(raw: Raw, now: datetime) -> None:
    raw["trainServices"][0].update(std="00:05", etd="00:12")
    service = normalise_board(raw, "WAT", now.replace(hour=23, minute=50)).services[0]
    assert (service.in_min, service.delay_min) == (15, 7)


def test_paging_and_walking_time(now: datetime) -> None:
    provider = DemoProvider()
    route = Route(
        id="walk",
        label="Walk",
        origin="SUR",
        destination="WAT",
        min_departure_minutes=15,
        page_size=3,
    )
    board = normalise_board(provider.board(route, 0, now).raw, "WAT", now)
    page = page_board(board, route, 0, provider)
    assert len(page.services) == 3 and page.services[0].in_min >= 15
    assert page.has_next and page.next_offset == page.services[-1].in_min
    assert page.earlier_offset == -45
    assert not page_board(board, route, 119, provider).has_next


def test_paging_preserves_same_minute_boundary(now: datetime) -> None:
    provider, route = DemoProvider(), defaults().routes[0]
    raw = {
        "trainServices": [{"serviceID": str(i), "std": f"18:{5 + i // 2:02d}"} for i in range(10)]
    }
    board = normalise_board(raw, "WAT", now)
    first = page_board(board, route, 0, provider, now)
    cursor = read_cursor(first.next_cursor, route, now)
    second = page_board(board, route, cursor_offset(cursor, now), provider, now, cursor)
    assert [service.id for service in first.services + second.services] == list(map(str, range(10)))


def test_cursor_survives_minute_change_across_midnight(now: datetime) -> None:
    provider, route = DemoProvider(), defaults().routes[0]
    now = now.replace(hour=23, minute=50, second=50)
    start = now.replace(minute=54, second=0)
    raw = {
        "trainServices": [
            {"serviceID": str(i), "std": (start + timedelta(minutes=i)).strftime("%H:%M")}
            for i in range(10)
        ]
    }
    first = page_board(normalise_board(raw, "WAT", now), route, 0, provider, now)
    later = now + timedelta(minutes=2)
    cursor = read_cursor(first.next_cursor, route, later)
    offset = cursor_offset(cursor, later)
    second = page_board(
        normalise_board(raw, "WAT", later),
        route,
        offset,
        provider,
        later,
        cursor,
    )
    assert first.services[-1].planned == "00:00"
    assert second.services[0].planned == "00:01"
    assert {s.id for s in first.services}.isdisjoint(s.id for s in second.services)


def test_full_upstream_page_does_not_end_paging(now: datetime) -> None:
    provider = DemoProvider()
    route = defaults().routes[0].model_copy(update={"page_size": 10})
    raw = {"trainServices": [{"serviceID": str(i), "std": f"18:{i:02d}"} for i in range(10)]}
    page = page_board(normalise_board(raw, "WAT", now), route, 0, provider, now)
    assert len(page.services) == 10 and page.has_next


def test_paging_stays_in_anchored_two_hour_window(now: datetime) -> None:
    provider, route = DemoProvider(), defaults().routes[0]
    now = now.replace(hour=23, minute=40)
    first = page_board(
        normalise_board(provider.board(route, 0, now).raw, "WAT", now), route, 0, provider, now
    )
    cursor = read_cursor(first.next_cursor, route, now)
    offset = cursor_offset(cursor, now)
    last = page_board(
        normalise_board(provider.board(route, offset, now).raw, "WAT", now),
        route,
        offset,
        provider,
        now,
        cursor,
    )
    assert last.services[-1].planned == "01:35" and last.services[-1].in_min == 115
    assert not last.has_next
    earlier = page_board(
        normalise_board(provider.board(route, -45, now).raw, "WAT", now), route, -45, provider, now
    )
    assert earlier.services[0].in_min == -45


def test_invalid_config_falls_back_without_overwrite(tmp_path: Path) -> None:
    assert load_config(tmp_path).warning == "config_missing"
    path = tmp_path / "routes.json"
    path.write_text("{broken")
    assert load_config(tmp_path).warning == "config_invalid"
    assert path.read_text() == "{broken"


def test_route_validation() -> None:
    route = defaults().routes[0]
    with pytest.raises(ValidationError):
        RouteConfig(routes=[route, route])
    with pytest.raises(ValidationError):
        Route(id="bad", label="Bad", origin="ZZZ", destination="WAT")
    with pytest.raises(ValidationError):
        Route(id="bad", label="Bad", origin="SUR", destination="WAT", page_size=0)


def test_route_return_journey_persists_as_one_document(tmp_path: Path) -> None:
    store = RouteStore(tmp_path)
    store.write(
        RouteWrite(
            id="new",
            label="Woking to Surbiton",
            origin="WOK",
            destination="SUR",
            add_return_journey=True,
        ),
        "create",
    )
    saved = load_config(tmp_path)
    assert saved.source == "file" and len(saved.config.routes) == 4
    reverse = saved.config.routes[-1]
    assert (reverse.origin, reverse.destination) == ("SUR", "WOK")
    store.write("new-return", "delete")
    assert len(load_config(tmp_path).config.routes) == 3


def test_route_order_rejects_changed_membership(tmp_path: Path) -> None:
    from app.routes import RouteConflict

    store = RouteStore(tmp_path)
    store.reorder(["back", "out"])
    with pytest.raises(RouteConflict):
        store.reorder(["back", "back"])
    assert [route.id for route in load_config(tmp_path).config.routes] == ["back", "out"]
