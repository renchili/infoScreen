from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from surface import serve_infoscreen

pytestmark = pytest.mark.integration


@pytest.fixture()
def http_base(monkeypatch: pytest.MonkeyPatch, seeded_env: Path):
    monkeypatch.setattr(serve_infoscreen, "ENV_DIR", seeded_env)
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve_infoscreen.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fetch_text(base: str, path: str) -> str:
    with urllib.request.urlopen(base + path, timeout=5) as response:
        return response.read().decode("utf-8")


def fetch_json(base: str, path: str):
    return json.loads(fetch_text(base, path))


def test_http_dashboard_and_openapi_are_served(http_base: str) -> None:
    html = fetch_text(http_base, "/")
    spec = fetch_json(http_base, "/openapi.json")

    assert "assets/js/dashboard.js" in html
    assert "assets/js/local_event_card.js" in html
    assert spec["info"]["title"] == "InfoScreen Local API"


def test_http_runtime_json_uses_seeded_fixture_data(http_base: str) -> None:
    market = fetch_json(http_base, "/market.json")
    events = fetch_json(http_base, "/local_event_search_results.json")
    news = fetch_json(http_base, "/event_stream.json")

    assert market["items"][0]["symbol"] == "AAPL"
    assert events["results"][0]["title"] == "Fixture Community Fitness Session"
    assert news["items_by_lang"]["zh"][0]["title"] == "中文测试标题"


def test_http_public_photo_fixture_is_served(http_base: str) -> None:
    assert fetch_text(http_base, "/public_photos/fixture-photo.txt") == "fixture photo bytes\n"
