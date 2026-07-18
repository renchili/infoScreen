from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from surface import serve_infoscreen
from surface.local_events_runtime.studio_capture import write_snapshot

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\nfixture-png"
SNAPSHOT_ID = "20260719T040506123456Z-4183667b5e"
LISTING_URL = "https://www.esplanade.com/whats-on"


@pytest.fixture()
def studio_http_base(monkeypatch: pytest.MonkeyPatch, seeded_env: Path):
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


def request_json(base: str, path: str, method: str, payload: dict | None = None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def error_json(base: str, path: str, method: str, payload: dict, expected: int) -> dict:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == expected
    return json.loads(caught.value.read().decode("utf-8"))


def metadata(element_count: int = 1) -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "source_id": "esplanade",
        "source_name": "Esplanade",
        "listing_url": LISTING_URL,
        "final_url": LISTING_URL,
        "page_title": "What's On",
        "captured_at": "2026-07-19T04:05:06.123456+00:00",
        "prepare": {},
        "dom_element_count": element_count,
        "dom_truncated": False,
        "assets": {"screenshot": "page.png", "html": "page.html", "dom": "dom.json"},
    }


def node(
    node_id: str,
    parent_id: str | None,
    tag: str,
    classes: str = "",
    text: str = "",
    href: str = "",
) -> dict:
    attributes = {"class": classes} if classes else {}
    if href:
        attributes["href"] = href
    return {
        "id": node_id,
        "parent_id": parent_id,
        "tag": tag,
        "selector": tag,
        "text": text,
        "href": href,
        "src": "",
        "attributes": attributes,
        "rect": {"x": 0, "y": 0, "width": 100, "height": 20},
    }


def test_dom() -> dict:
    elements = [
        node("root", None, "main", "events-list"),
        node("card", "root", "article", "event-card"),
        node("title", "card", "h2", "event-title", "Future Music Session"),
        node("date", "card", "time", "event-date", "19 Jul 2099"),
        node("venue", "card", "div", "event-venue", "Esplanade Recital Studio"),
        node("link", "card", "a", "event-link", "Details", "https://www.esplanade.com/whats-on/festivals-and-series/future-music-session"),
        node("summary", "card", "p", "event-summary", "A real listed performance."),
    ]
    return {
        "schema_version": 1,
        "page": {"document_width": 1440, "document_height": 2200},
        "candidate_count": len(elements),
        "element_count": len(elements),
        "truncated": False,
        "elements": elements,
    }


def valid_draft() -> dict:
    return {
        "schema_version": 1,
        "source_id": "esplanade",
        "listing_url": LISTING_URL,
        "version": 0,
        "status": "draft",
        "card": {"selector": "main.events-list > article.event-card", "exclude_selectors": []},
        "fields": {
            "title": {"selector": "h2.event-title"},
            "when": {"selector": "time.event-date"},
            "where": {"selector": "div.event-venue", "allow_source_default": False},
            "url": {"selector": "a.event-link[href]", "attribute": "href"},
            "summary": {"selector": "p.event-summary", "optional": True},
        },
        "detail_page": {"enabled": False, "fields": {}},
        "validation": {"require_public_detail_url": True, "require_current_or_future_date": True},
    }


def test_http_capture_uses_one_shot_job_and_active_env_dir(
    studio_http_base: str,
    seeded_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"ok": True, "snapshot": metadata(20)}) + "\n",
            stderr="",
        )

    monkeypatch.setattr(serve_infoscreen.subprocess, "run", fake_run)
    status, payload = request_json(
        studio_http_base,
        "/api/local-events/studio/capture",
        "POST",
        {"source_id": "esplanade", "listing_url": LISTING_URL},
    )

    assert status == 200
    assert payload["snapshot"]["snapshot_id"] == SNAPSHOT_ID
    command = observed["command"]
    assert command[1].endswith("surface/jobs/local_event_studio_capture.py")
    assert command[-2:] == ["esplanade", LISTING_URL]
    assert observed["kwargs"]["env"]["INFOSCREEN_ENV_DIR"] == str(seeded_env)
    assert observed["kwargs"]["cwd"] == str(serve_infoscreen.SURFACE_DIR)


def test_http_snapshot_catalog_and_assets_are_served_from_local_runtime(
    studio_http_base: str,
    seeded_env: Path,
) -> None:
    write_snapshot(
        seeded_env / "local_event_studio",
        metadata(),
        screenshot=PNG,
        html="<html><body>fixture</body></html>",
        dom={
            "schema_version": 1,
            "page": {"document_width": 1440, "document_height": 2200},
            "candidate_count": 1,
            "element_count": 1,
            "truncated": False,
            "elements": [],
        },
    )

    query = urllib.parse.urlencode({"source_id": "esplanade", "listing_url": LISTING_URL})
    with urllib.request.urlopen(
        studio_http_base + f"/api/local-events/studio/snapshots?{query}",
        timeout=5,
    ) as response:
        catalog = json.loads(response.read().decode("utf-8"))
    assert [item["snapshot_id"] for item in catalog["snapshots"]] == [SNAPSHOT_ID]

    asset_query = urllib.parse.urlencode(
        {"source_id": "esplanade", "snapshot_id": SNAPSHOT_ID, "asset": "page.png"}
    )
    asset_url = studio_http_base + f"/api/local-events/studio/snapshot-asset?{asset_query}"
    with urllib.request.urlopen(asset_url, timeout=5) as response:
        assert response.headers["Content-Type"] == "image/png"
        assert response.read() == PNG

    head = urllib.request.Request(asset_url, method="HEAD")
    with urllib.request.urlopen(head, timeout=5) as response:
        assert response.status == 200
        assert int(response.headers["Content-Length"]) == len(PNG)


def test_http_draft_test_is_required_before_publication(
    studio_http_base: str,
    seeded_env: Path,
) -> None:
    write_snapshot(
        seeded_env / "local_event_studio",
        metadata(7),
        screenshot=PNG,
        html="<html><body>fixture</body></html>",
        dom=test_dom(),
    )
    status, _ = request_json(
        studio_http_base,
        "/api/local-events/studio/draft",
        "PUT",
        valid_draft(),
    )
    assert status == 200

    binding = {"source_id": "esplanade", "listing_url": LISTING_URL}
    rejected = error_json(
        studio_http_base,
        "/api/local-events/studio/publish",
        "POST",
        binding,
        422,
    )
    assert rejected["error"] == "studio_test_required"

    status, tested = request_json(
        studio_http_base,
        "/api/local-events/studio/test",
        "POST",
        {**binding, "snapshot_id": SNAPSHOT_ID},
    )
    assert status == 200
    assert tested["result"]["publishable"] is True
    assert tested["result"]["accepted_count"] == 1
    assert tested["result"]["accepted"][0]["event"]["title"] == "Future Music Session"

    latest_query = urllib.parse.urlencode(binding)
    with urllib.request.urlopen(
        studio_http_base + f"/api/local-events/studio/test-latest?{latest_query}",
        timeout=5,
    ) as response:
        latest = json.loads(response.read().decode("utf-8"))
    assert latest["result"]["run_id"] == tested["result"]["run_id"]

    status, published = request_json(
        studio_http_base,
        "/api/local-events/studio/publish",
        "POST",
        binding,
    )
    assert status == 200
    assert published["rule"]["version"] == 1


def test_http_snapshot_asset_rejects_path_components(studio_http_base: str) -> None:
    query = urllib.parse.urlencode(
        {"source_id": "../outside", "snapshot_id": SNAPSHOT_ID, "asset": "page.png"}
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(
            studio_http_base + f"/api/local-events/studio/snapshot-asset?{query}",
            timeout=5,
        )
    assert caught.value.code == 404
