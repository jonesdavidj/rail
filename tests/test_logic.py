"""Focused tests for silent data/config/paging mistakes; no exhaustive matrices."""

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Route, RouteConfig, RouteWrite, defaults, load_config
from app.normalise import Raw, normalise_board
from app.paging import page_board
from app.providers import DemoProvider
from app.routes import RouteStore


@pytest.fixture
def raw() -> Raw:
    return json.loads((Path(__file__).parent / "fixtures/board.json").read_text())


def test_delay_and_destination_arrival(raw: Raw, now: datetime) -> None:
    service = normalise_board(raw, "WAT", now).services[0]
    assert (service.status, service.delay_min, service.expected) == ("late", 7, "18:12")
    assert service.arrival and service.arrival.expected == "18:36"
    assert service.length == 8


def test_unknown_estimates_and_missing_length(raw: Raw, now: datetime) -> None:
    raw["trainServices"][0].update(etd="No report", length=None, platform=None)
    service = normalise_board(raw, "WAT", now).services[0]
    assert service.status == "unknown" and service.expected is None and service.length is None
    raw["trainServices"][0]["etd"] = "Delayed"
    assert normalise_board(raw, "WAT", now).services[0].status == "delayed"


def test_on_time(raw: Raw, now: datetime) -> None:
    raw["trainServices"][0]["etd"] = "On time"
    service = normalise_board(raw, "WAT", now).services[0]
    assert service.status == "on_time" and service.delay_min == 0 and service.expected is None


def test_cancellation_and_reason(raw: Raw, now: datetime) -> None:
    raw["trainServices"][0].update(isCancelled=True, etd="Cancelled", cancelReason="Crew shortage")
    service = normalise_board(raw, "WAT", now).services[0]
    assert service.status == "cancelled" and service.reason == "Crew shortage"
    assert service.arrival and service.arrival.cancelled


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
    assert page.has_next and page.next_offset == page.services[-1].in_min + 1
    assert page.earlier_offset == -45
    assert not page_board(board, route, 119, provider).has_next


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
