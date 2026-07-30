from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


def test_script_calls_the_production_preview_function_without_copying_collection_logic(
    monkeypatch,
) -> None:
    script = load_script()
    calls = []
    store = object()
    state_payload = {
        "listing_pages": [],
        "events": [
            {
                "detail_url": (
                    "https://www.marinabaysands.com/museum/exhibitions/"
                    "another-world-is-possible.html"
                ),
                "title": "raw production value",
                "when": "raw production date value",
                "detail_status": "raw production status",
                "detail_error": "raw production error",
            }
        ],
        "event_collection": {"raw": True},
    }

    class State:
        def model_dump(self, *, mode):
            assert mode == "json"
            return state_payload

    server = ModuleType("surface.serve_infoscreen")
    server.review_store = lambda: store

    def preview_event_candidates(actual_store, listing_url):
        calls.append((actual_store, listing_url))
        return State()

    server.preview_event_candidates = preview_event_candidates
    surface = ModuleType("surface")
    surface.serve_infoscreen = server
    monkeypatch.setitem(sys.modules, "surface", surface)
    monkeypatch.setitem(sys.modules, "surface.serve_infoscreen", server)

    payload, returncode = script.collect_payload(LISTING_URL)

    assert returncode == 0
    assert calls == [(store, LISTING_URL)]
    assert payload == {"ok": True, "preview": True, **state_payload}


def test_script_keeps_production_error_shapes(monkeypatch) -> None:
    script = load_script()
    surface = ModuleType("surface")
    server = ModuleType("surface.serve_infoscreen")
    server.review_store = lambda: object()

    def preview_event_candidates(store, listing_url):
        raise ValueError("listing page is not present in review state")

    server.preview_event_candidates = preview_event_candidates
    surface.serve_infoscreen = server
    monkeypatch.setitem(sys.modules, "surface", surface)
    monkeypatch.setitem(sys.modules, "surface.serve_infoscreen", server)

    payload, returncode = script.collect_payload(LISTING_URL)

    assert returncode == 2
    assert payload == {
        "ok": False,
        "error": "event_preview_request_failed",
        "detail": "listing page is not present in review state",
    }


def test_script_is_a_thin_production_entrypoint() -> None:
    source = read_text("scripts/collect_local_event_preview.py")

    assert "from surface import serve_infoscreen as server" in source
    assert "server.preview_event_candidates(" in source
    assert "server.review_store()" in source
    assert "state.model_dump(mode=\"json\")" in source
    assert "playwright" not in source
    assert "preview_listing_evidence_only" not in source
    assert "another-world-is-possible" not in source
    assert "urllib" not in source
    assert "requests" not in source
