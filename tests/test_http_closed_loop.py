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


def test_http_local_event_details_are_plain_text_for_stale_runtime(
    http_base: str,
    seeded_env: Path,
) -> None:
    raw_details = (
        "&amp;lt;p&amp;gt;&amp;lt;strong&amp;gt;About the Event&amp;lt;/strong&amp;gt;"
        "&amp;lt;span style=&amp;quot;background-color: transparent;&amp;quot;&amp;gt;"
        "&amp;lt;/span&amp;gt;&amp;lt;/p&amp;gt;"
        "&amp;lt;p&amp;gt;This talk is a compassionate and practical guide to navigating loss."
        "&amp;lt;/p&amp;gt;"
    )
    payload = {
        "results": [
            {
                "title": "What Happens After Someone Dies: A Practical Guide for Families",
                "when": "14 Jul 2099",
                "start_date": "2099-07-14",
                "end_date": "2099-07-14",
                "where": "Central Public Library",
                "description": raw_details,
                "url": "https://example.test/events/practical-guide",
                "candidate_policy": "official-listing-authority-v1",
            }
        ]
    }
    (seeded_env / "local_event_search_results.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    expected = "This talk is a compassionate and practical guide to navigating loss."
    for path in ("/local_event_search_results.json", "/api/local-events/search"):
        delivered = fetch_json(http_base, path)
        event = delivered["results"][0]
        assert event["summary"] == expected
        assert event["description"] == expected
        assert "<" not in event["summary"]
        assert "&lt;" not in event["summary"]
        assert delivered["text_normalizer"] == "plain-text-v1"


def test_http_public_photo_fixture_is_served(http_base: str) -> None:
    assert fetch_text(http_base, "/public_photos/fixture-photo.txt") == "fixture photo bytes\n"
