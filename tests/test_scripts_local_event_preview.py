from __future__ import annotations

import importlib.util
import io
import json
from urllib.error import HTTPError, URLError

from .conftest import ROOT, read_text


SCRIPT_PATH = ROOT / "scripts" / "collect_local_event_preview.py"
LISTING_URL = (
    "https://www.marinabaysands.com/museum/about-us/exhibition-archive.html"
)


def load_script():
    spec = importlib.util.spec_from_file_location(
        "infoscreen_collect_local_event_preview",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_calls_running_preview_route_and_returns_raw_body(monkeypatch) -> None:
    script = load_script()
    raw_body = b'{"ok":true,"preview":true,"events":[{"raw":"service"}]}'
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return raw_body

    def fake_urlopen(request, *, timeout):
        calls.append((request, timeout))
        return Response()

    monkeypatch.setattr(script, "urlopen", fake_urlopen)

    body, status = script.fetch_raw_response(LISTING_URL)

    assert body is raw_body
    assert status == 200
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == script.PREVIEW_URL
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {"listing_url": LISTING_URL}
    assert timeout == script.PREVIEW_TIMEOUT_SECONDS


def test_script_preserves_raw_http_error_response(monkeypatch) -> None:
    script = load_script()
    raw_body = b'{"ok":false,"error":"event_preview_collection_failed"}'

    def fake_urlopen(request, *, timeout):
        raise HTTPError(
            request.full_url,
            500,
            "Internal Server Error",
            {},
            io.BytesIO(raw_body),
        )

    monkeypatch.setattr(script, "urlopen", fake_urlopen)

    body, status = script.fetch_raw_response(LISTING_URL)

    assert body == raw_body
    assert status == 500


def test_script_reports_service_transport_failure_separately(monkeypatch) -> None:
    script = load_script()

    def fake_urlopen(request, *, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(script, "urlopen", fake_urlopen)

    body, status = script.fetch_raw_response(LISTING_URL)
    payload = json.loads(body.decode("utf-8"))

    assert status == 0
    assert payload == {
        "ok": False,
        "error": "preview_service_unreachable",
        "detail": "connection refused",
        "service_url": script.PREVIEW_URL,
    }


def test_script_is_only_a_raw_client_for_the_existing_service() -> None:
    source = read_text("scripts/collect_local_event_preview.py")

    assert (
        'PREVIEW_URL = "http://127.0.0.1:8765/api/local-events/review/preview-events"'
        in source
    )
    assert "urlopen(request" in source
    assert "response.read()" in source
    assert "from surface" not in source
    assert "serve_infoscreen" not in source
    assert "preview_event_candidates" not in source
    assert "collect_event_candidates" not in source
    assert "playwright" not in source
    assert "preview_listing_evidence_only" not in source
    assert "another-world-is-possible" not in source
    assert "json.loads" not in source
