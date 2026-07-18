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


def test_http_capture_uses_one_shot_job_and_active_env_dir(
    studio_http_base: str,
    seeded_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict = {}
    metadata = {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "source_id": "esplanade",
        "source_name": "Esplanade",
        "listing_url": "https://www.esplanade.com/whats-on",
        "final_url": "https://www.esplanade.com/whats-on",
        "page_title": "What's On",
        "captured_at": "2026-07-19T04:05:06.123456+00:00",
        "prepare": {},
        "dom_element_count": 20,
        "dom_truncated": False,
        "assets": {"screenshot": "page.png", "html": "page.html", "dom": "dom.json"},
    }

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"ok": True, "snapshot": metadata}) + "\n",
            stderr="",
        )

    monkeypatch.setattr(serve_infoscreen.subprocess, "run", fake_run)
    status, payload = request_json(
        studio_http_base,
        "/api/local-events/studio/capture",
        "POST",
        {
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
        },
    )

    assert status == 200
    assert payload["snapshot"]["snapshot_id"] == SNAPSHOT_ID
    command = observed["command"]
    assert command[1].endswith("surface/jobs/local_event_studio_capture.py")
    assert command[-2:] == ["esplanade", "https://www.esplanade.com/whats-on"]
    assert observed["kwargs"]["env"]["INFOSCREEN_ENV_DIR"] == str(seeded_env)
    assert observed["kwargs"]["cwd"] == str(serve_infoscreen.SURFACE_DIR)


def test_http_snapshot_catalog_and_assets_are_served_from_local_runtime(
    studio_http_base: str,
    seeded_env: Path,
) -> None:
    metadata = {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "source_id": "esplanade",
        "source_name": "Esplanade",
        "listing_url": "https://www.esplanade.com/whats-on",
        "final_url": "https://www.esplanade.com/whats-on",
        "page_title": "What's On",
        "captured_at": "2026-07-19T04:05:06.123456+00:00",
        "prepare": {},
        "dom_element_count": 1,
        "dom_truncated": False,
        "assets": {"screenshot": "page.png", "html": "page.html", "dom": "dom.json"},
    }
    dom = {
        "schema_version": 1,
        "page": {"document_width": 1440, "document_height": 2200},
        "candidate_count": 1,
        "element_count": 1,
        "truncated": False,
        "elements": [],
    }
    write_snapshot(
        seeded_env / "local_event_studio",
        metadata,
        screenshot=PNG,
        html="<html><body>fixture</body></html>",
        dom=dom,
    )

    query = urllib.parse.urlencode(
        {
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
        }
    )
    with urllib.request.urlopen(
        studio_http_base + f"/api/local-events/studio/snapshots?{query}",
        timeout=5,
    ) as response:
        catalog = json.loads(response.read().decode("utf-8"))
    assert [item["snapshot_id"] for item in catalog["snapshots"]] == [SNAPSHOT_ID]

    asset_query = urllib.parse.urlencode(
        {
            "source_id": "esplanade",
            "snapshot_id": SNAPSHOT_ID,
            "asset": "page.png",
        }
    )
    asset_url = studio_http_base + f"/api/local-events/studio/snapshot-asset?{asset_query}"
    with urllib.request.urlopen(asset_url, timeout=5) as response:
        assert response.headers["Content-Type"] == "image/png"
        assert response.read() == PNG

    head = urllib.request.Request(asset_url, method="HEAD")
    with urllib.request.urlopen(head, timeout=5) as response:
        assert response.status == 200
        assert int(response.headers["Content-Length"]) == len(PNG)


def test_http_snapshot_asset_rejects_path_components(studio_http_base: str) -> None:
    query = urllib.parse.urlencode(
        {
            "source_id": "../outside",
            "snapshot_id": SNAPSHOT_ID,
            "asset": "page.png",
        }
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(
            studio_http_base + f"/api/local-events/studio/snapshot-asset?{query}",
            timeout=5,
        )
    assert caught.value.code == 404
