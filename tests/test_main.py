import http.client
import http.server
import json
import threading

import pytest

from app.main import Handler


@pytest.fixture
def server(monkeypatch):
    monkeypatch.delenv("RAIL_DATA_API_KEY", raising=False)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield server
        server.shutdown()
        thread.join()


def test_health_without_api_key(server):
    connection = http.client.HTTPConnection(*server.server_address)
    connection.request("GET", "/api/health")
    response = connection.getresponse()
    assert response.status == 200
    assert json.loads(response.read()) == {
        "status": "ok", "service": "rail", "mode": "demo"
    }
    connection.close()


def test_unknown_path_is_not_healthy(server):
    connection = http.client.HTTPConnection(*server.server_address)
    connection.request("GET", "/missing")
    assert connection.getresponse().status == 404
    connection.close()
