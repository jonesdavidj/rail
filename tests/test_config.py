import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Route, RouteConfig, defaults, load_config


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""),
        ("id", "a b"),
        ("id", "a" * 65),
        ("label", " "),
        ("label", "a\nb"),
        ("label", "a" * 101),
        ("origin", "sur"),
        ("origin", "ZZZ"),
        ("origin", "SURR"),
        ("origin", 123),
        ("destination", "SUR"),
        ("destination", "ZZZ"),
        ("min_departure_minutes", -1),
        ("min_departure_minutes", 121),
        ("min_departure_minutes", True),
        ("min_departure_minutes", "5"),
        ("page_size", 0),
        ("page_size", 26),
        ("page_size", 1.5),
        ("page_size", True),
        ("unexpected", "anything"),
    ],
)
def test_route_validation(field: str, value: object) -> None:
    raw = defaults().routes[0].model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        Route.model_validate(raw)


def test_unique_ids_and_limits() -> None:
    route = defaults().routes[0]
    with pytest.raises(ValidationError):
        RouteConfig(routes=[route, route])
    with pytest.raises(ValidationError):
        RouteConfig.model_validate({"routes": [], "version": True})
    with pytest.raises(ValidationError):
        RouteConfig.model_validate({"routes": [], "version": 2})
    with pytest.raises(ValidationError):
        RouteConfig(routes=[route] * 33)


def test_missing_defaults(tmp_path: Path) -> None:
    result = load_config(tmp_path)
    assert result.source == "defaults" and result.warning == "config_missing"
    assert [(route.origin, route.destination) for route in result.config.routes] == [
        ("SUR", "WAT"),
        ("WAT", "SUR"),
    ]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "payload", [b"{", b"\xff", b"[]", b"{}", b'{"routes":null}', b'{"routes": [], "version":2}']
)
def test_invalid_config_falls_back(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "routes.json"
    path.write_bytes(payload)
    result = load_config(tmp_path)
    assert result.source == "defaults" and result.warning == "config_invalid"
    assert path.read_bytes() == payload


def test_valid_file_and_empty_routes(tmp_path: Path) -> None:
    path = tmp_path / "routes.json"
    path.write_text(defaults().model_dump_json())
    assert load_config(tmp_path).source == "file"
    path.write_text(json.dumps({"version": 1, "routes": []}))
    assert load_config(tmp_path).config.routes == []


def test_unreadable_and_oversize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "routes.json"
    path.write_text(" " * 256_001)
    assert load_config(tmp_path).warning == "config_too_large"
    path.unlink()
    path.mkdir()
    assert load_config(tmp_path).warning == "config_unreadable"
    path.rmdir()
    path.write_text("{}")

    def denied(self: Path) -> bytes:
        raise PermissionError("private information")

    monkeypatch.setattr(Path, "read_bytes", denied)
    assert load_config(tmp_path).warning == "config_unreadable"
