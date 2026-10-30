import json
import logging
import socket

import pytest

from app.logging import JsonFormatter


def test_structured_event() -> None:
    record = logging.LogRecord("rail", logging.INFO, "", 0, "config_loaded", (), None)
    record.fields = {"source": "defaults"}
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "config_loaded"
    assert payload["fields"] == {"source": "defaults"}
    assert payload["level"] == "INFO"
    assert payload["timestamp"]


def test_network_guard() -> None:
    with pytest.raises(AssertionError, match="forbidden"):
        socket.create_connection(("example.com", 443))
