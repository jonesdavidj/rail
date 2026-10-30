"""Small documented fixture and public error mapping; no live transport calls."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.rail_data import ProviderError, http_error, parse_board, transport_error


def test_documented_board_and_bad_json(now: datetime) -> None:
    body = (Path(__file__).parent / "fixtures/board.json").read_bytes()
    assert parse_board(body, "WAT", now)["crs"] == "SUR"
    with pytest.raises(ProviderError, match="invalid JSON"):
        parse_board(b"<html>not JSON</html>", "WAT", now)
    with pytest.raises(ProviderError, match="invalid JSON"):
        parse_board(json.dumps({"error": "bad key"}).encode(), "WAT", now)


def test_error_mapping() -> None:
    assert http_error(401).code == http_error(403).code == "authentication"
    assert http_error(429, "120").retry_after == 120
    assert http_error(404).code == "routing"
    assert http_error(302).code == "redirect"


def test_timeout_mapping() -> None:
    assert transport_error(TimeoutError()).code == "timeout"
    assert transport_error(TimeoutError()).status == 504
