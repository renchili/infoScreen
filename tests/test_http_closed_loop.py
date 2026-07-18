from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
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


def request_json(base: str, path: str, method: str, payload: dict | None = None):
    data = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def assert_http_status(
    base: str,
    path: str,
    method: str,
    expected: int,
    payload: dict | None = None,
) -> dict:
    data = None
    headers = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(base + path, data=data, headers=headers or {}, method=method)
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == expected
    return json.loads(caught.value.read().decode("utf-8"))


def studio_draft() -> dict:
    return {
        "schema_version": 1,
        "source_id": "esplanade",
        "listing_url": "https://www.esplanade.com/whats-on",
        "version": 0,
        "status": "draft",
        "card": {
            "selector": "main .event-card",
            "exclude_selectors": [".promotion-card"],
        },
        "fields": {
            "title": {"selector": "h2"},
            "when": {"selector": ".event-date"},
            "where": {
                "selector": ".event-venue",
                "allow_source_default": False,
            },
            "url": {"selector": "a[href]", "attribute": "href"},
            "summary": {"selector": ".event-description", "optional": True},
        },
        "detail_page": {
            "enabled": True,
            "fields": {
                "when": {"selector": ".detail-date"},
                "where": {
                    "selector": ".detail-venue",
                    "allow_source_default": False,
                },
            },
        },
        "validation": {
            "require_public_detail_url": True,
            "require_current_or_future_date": True,
        },
    }


def test_http_dashboard_and_openapi_are_served(http_base: str) -> None:
    html = fetch_text(http_base, "/")
    spec = fetch_json(http_base, "/openapi.json")

    assert "assets/js/dashboard.js" in html
    assert "assets/js/local_event_card.js" in html
    assert spec["info"]["title"] == "InfoScreen Local API"
    assert spec["servers"][0]["url"] == "http://127.0.0.1:8765"
    assert "/api/local-events/studio/draft" in spec["paths"]
    assert "/api/local-events/studio/test" in spec["paths"]


def test_http_runtime_json_uses_seeded_fixture_data(http_base: str) -> None:
    market = fetch_json(http_base, "/market.json")
    events = fetch_json(http_base, "/local_event_search_results.json")
    news = fetch_json(http_base, "/event_stream.json")

    assert market["items"][0]["symbol"] == "AAPL"
    assert events["results"][0]["title"] == "Fixture Community Fitness Session"
    assert news["items_by_lang"]["zh"][0]["title"] == "中文测试标题"


def test_http_studio_rule_lifecycle_uses_existing_server(
    http_base: str,
    seeded_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = fetch_json(http_base, "/api/local-events/studio/sources")
    esplanade = next(item for item in sources["sources"] if item["source_id"] == "esplanade")
    assert esplanade["listing_urls"][0]["published_version"] is None

    status, saved = request_json(
        http_base,
        "/api/local-events/studio/draft",
        "PUT",
        studio_draft(),
    )
    assert status == 200
    assert saved["rule"]["status"] == "draft"

    query = urllib.parse.urlencode(
        {
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
        }
    )
    state = fetch_json(http_base, f"/api/local-events/studio/rules?{query}")
    assert state["draft"]["card"]["selector"] == "main .event-card"
    assert state["published"] is None

    monkeypatch.setattr(
        serve_infoscreen,
        "require_publishable_test",
        lambda draft, root: {"publishable": True, "rule_fingerprint": "fixture"},
    )
    status, published = request_json(
        http_base,
        "/api/local-events/studio/publish",
        "POST",
        {
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
        },
    )
    assert status == 200
    assert published["rule"]["version"] == 1
    assert published["rule"]["status"] == "published"

    exported = fetch_json(http_base, f"/api/local-events/studio/export?{query}")
    assert exported["rule"]["version"] == 1

    status, imported = request_json(
        http_base,
        "/api/local-events/studio/import",
        "POST",
        {"rule": exported["rule"]},
    )
    assert status == 200
    assert imported["rule"]["status"] == "draft"
    assert imported["rule"]["version"] == 0

    status, deleted = request_json(
        http_base,
        "/api/local-events/studio/draft",
        "DELETE",
        {
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
        },
    )
    assert status == 200
    assert deleted == {"ok": True, "deleted": True}

    status, rolled_back = request_json(
        http_base,
        "/api/local-events/studio/rollback",
        "POST",
        {
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
            "version": 1,
        },
    )
    assert status == 200
    assert rolled_back["rule"]["version"] == 2
    assert rolled_back["rule"]["based_on_version"] == 1

    final_state = fetch_json(http_base, f"/api/local-events/studio/rules?{query}")
    assert [item["version"] for item in final_state["history"]] == [1, 2]
    assert final_state["published"]["version"] == 2
    assert (seeded_env / "local_event_studio" / "rules").is_dir()


def test_http_studio_rejects_unconfigured_listing(http_base: str) -> None:
    bad = studio_draft()
    bad["listing_url"] = "https://www.esplanade.com/not-configured"
    error = assert_http_status(
        http_base,
        "/api/local-events/studio/draft",
        "PUT",
        400,
        bad,
    )
    assert error["error"] == "unknown_listing"


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
    request = urllib.request.Request(http_base + "/public_photos/fixture-photo.txt", method="HEAD")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert int(response.headers["Content-Length"]) > 0


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    "path",
    [
        "/public_photos/%2e%2e/market.json",
        "/public_photos/%2E%2E%2Fmarket.json",
        "/public_photos/%2Fetc%2Fpasswd",
        "/public_photos/..%5cmarket.json",
        "/public_photos/%00fixture-photo.txt",
    ],
)
def test_http_public_photo_traversal_is_rejected(
    http_base: str,
    path: str,
    method: str,
) -> None:
    assert_http_status(http_base, path, method, 404)


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_http_public_photo_symlink_escape_is_rejected(
    http_base: str,
    seeded_env: Path,
    method: str,
) -> None:
    secret = seeded_env / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    link = seeded_env / "public_photos" / "escape.txt"
    try:
        link.symlink_to(secret)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert_http_status(http_base, "/public_photos/escape.txt", method, 404)
