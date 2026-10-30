from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, defaults
from app.main import create_app
from app.normalise import Raw, normalise_board
from app.paging import page_board
from app.providers import DemoProvider, RailDataProvider
from tests.test_normalise import svc


def test_demo_scenarios_and_midnight(now: datetime) -> None:
    route = defaults().routes[0]
    provider = DemoProvider()
    for moment in (now, now.replace(hour=23, minute=50)):
        board = normalise_board(provider.board(route, 0, moment), route.destination, moment)
        assert {service.status for service in board.services} >= {
            "on_time",
            "late",
            "delayed",
            "cancelled",
        }
        assert any(service.platform is None for service in board.services)
        assert len({service.length for service in board.services}) > 2
        assert any(service.service_type == "bus" for service in board.services)
        assert all(service.arrival for service in board.services)
        assert any(service.planned.startswith("00:") for service in board.services) or moment == now


def test_demo_identity_stable(now: datetime) -> None:
    route = defaults().routes[0]
    provider = DemoProvider()
    first = provider.board(route, 0, now)["trainServices"]
    later = provider.board(route, 10, now)["trainServices"]
    assert {item["serviceID"] for item in later} & {item["serviceID"] for item in first}


@pytest.mark.parametrize("count", [0, 1, 7, 9])
def test_paging(now: datetime, count: int) -> None:
    route = defaults().routes[0]
    board = normalise_board(
        {
            "trainServices": [
                svc(std=f"18:{5 + index * 5:02d}", serviceID=str(index)) for index in range(count)
            ]
        },
        "WAT",
        now,
    )
    page = page_board(board, route, 0, DemoProvider())
    assert len(page.services) == min(count, 7)
    assert page.has_next == (count > 7)
    assert page.earlier_offset == -45
    if page.has_next:
        assert page.next_offset == page.services[-1].in_min + 1


def test_cap_walking_and_earlier(now: datetime) -> None:
    route = defaults().routes[0].model_copy(update={"page_size": 1, "min_departure_minutes": 10})
    board = normalise_board(
        {"trainServices": [svc(std="17:45"), svc(std="18:05"), svc(std="18:15"), svc(std="18:20")]},
        "WAT",
        now,
    )
    assert page_board(board, route, 0, DemoProvider()).services[0].planned == "18:15"
    early = page_board(board, route, -45, DemoProvider())
    assert early.services[0].planned == "17:45" and early.earlier_offset is None
    future = normalise_board({"trainServices": [svc(std="19:59"), svc(std="20:00")]}, "WAT", now)
    assert not page_board(future, route, 119, DemoProvider()).has_next


def test_api(tmp_path: Path, now: datetime) -> None:
    with TestClient(create_app(Settings(data_path=tmp_path), now=lambda: now)) as client:
        health = client.get("/api/health").json()
        assert health["demo"] and health["config_source"] == "defaults"
        assert health["config_warning"] == "config_missing"
        assert len(client.get("/api/routes").json()) == 2
        page = client.get("/api/board?route=out").json()
        assert page["demo"] and len(page["services"]) == 7 and page["has_next"]
        later = client.get("/api/board", params={"route": "out", "offset": page["next_offset"]})
        assert later.status_code == 200
        assert later.json()["services"][0]["in_min"] > page["services"][-1]["in_min"]
        assert client.get("/api/board?route=back&offset=-45").status_code == 200
        response = client.get("/", headers={"Host": "minisforum.lan:8097"})
        assert "DEMO DATA" in response.text and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "route=",
        "route=../out",
        "route=out&offset=120",
        "route=out&offset=-61",
        "route=out&offset=hello",
        "route=out&other=x",
        "route=out&route=back",
        "route=out&offset=0&offset=1",
    ],
)
def test_api_input(tmp_path: Path, query: str) -> None:
    with TestClient(create_app(Settings(data_path=tmp_path))) as client:
        assert client.get("/api/board?" + query).status_code == 422
        assert client.get("/api/board?route=unknown").status_code == 404


def test_live_stub_and_empty_config(tmp_path: Path, now: datetime) -> None:
    with TestClient(create_app(Settings(data_path=tmp_path), RailDataProvider())) as client:
        assert not client.get("/api/health").json()["provider_ready"]
        assert client.get("/api/board?route=out").status_code == 503
    (tmp_path / "routes.json").write_text('{"version":1,"routes":[]}')
    with TestClient(create_app(Settings(data_path=tmp_path), now=lambda: now)) as client:
        assert client.get("/api/routes").json() == []
        assert client.get("/api/health").json()["config_source"] == "file"


def test_malformed_provider(tmp_path: Path) -> None:
    class BrokenProvider(DemoProvider):
        def board(self, route: object, offset: int, now: datetime) -> Raw:
            return {"trainServices": "bad"}

    with TestClient(create_app(Settings(data_path=tmp_path), BrokenProvider())) as client:
        assert client.get("/api/board?route=out").status_code == 502


@pytest.mark.parametrize(
    "query",
    ["route=out&offset=1.0", "route=out&offset=+1", "route=out&offset=", "route=out&offset=1e1"],
)
def test_integer_offset_syntax(tmp_path: Path, query: str) -> None:
    with TestClient(create_app(Settings(data_path=tmp_path))) as client:
        assert client.get("/api/board?" + query).status_code == 422


@pytest.mark.parametrize("endpoint", ["/api/health", "/api/routes"])
def test_no_unexpected_parameters(tmp_path: Path, endpoint: str) -> None:
    with TestClient(create_app(Settings(data_path=tmp_path))) as client:
        assert client.get(endpoint + "?unexpected=value").status_code == 422


def test_configured_route_is_used(tmp_path: Path, now: datetime) -> None:
    config = defaults().model_dump()
    config["routes"] = [
        {
            "id": "custom",
            "label": "Woking to Waterloo",
            "origin": "WOK",
            "destination": "WAT",
            "min_departure_minutes": 15,
            "page_size": 3,
        }
    ]
    import json

    (tmp_path / "routes.json").write_text(json.dumps(config))
    with TestClient(create_app(Settings(data_path=tmp_path), now=lambda: now)) as client:
        board = client.get("/api/board?route=custom").json()
        assert board["title"] == "Woking to Waterloo"
        assert len(board["services"]) == 3
        assert all(row["in_min"] >= 15 for row in board["services"])
        assert client.get("/api/board?route=out").status_code == 404
