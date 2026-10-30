"""Every test is offline, including API integration tests."""

import socket
from datetime import datetime
from typing import NoReturn

import pytest

from app.normalise import LONDON


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Network calls are forbidden in tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 29, 18, 0, tzinfo=LONDON)
