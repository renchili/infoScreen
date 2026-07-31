from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from surface import serve_infoscreen
from surface.api_models import (
    LocalEventSearchResponse,
    MarketConfigRequest,
    MarketRefreshResponse,
    PhotosResponse,
)
from surface.openapi_spec import build_openapi

pytestmark = pytest.mark.backend


def test_runtime_json_returns_fixture_payload(monkeypatch: pytest.MonkeyPatch, seeded_env: Path) -> None:
    monkeypatch.setattr(serve_infoscreen, "ENV_DIR", seeded_env)
    market = serve_infoscreen.runtime_json("market.json")
    assert market["source"] == "fixture-market"
    assert market["items"][0]["symbol"] == "AAPL"


def test_openapi_covers_dashboard_mutations_and_actual_error_statuses() -> None:
    spec = build_openapi()
    paths = spec["paths"]
    assert spec["openapi"].startswith("3.1")
    assert "/api/market-config" in paths
    assert "/api/market-refresh" in paths
    assert "/api/local-events/search" in paths
    assert "/public_photos/{path}" in paths

    assert "404" not in paths["/api/local-events/search"]["get"]["responses"]
    assert "404" not in paths["/local_event_search_results.json"]["get"]["responses"]
    assert "504" in paths["/api/local-events/search"]["post"]["responses"]
    assert "sanitized" not in paths["/"]["get"]["description"].lower()


def test_openapi_describes_preview_selection_commit_and_formal_collection_boundary() -> None:
    paths = build_openapi()["paths"]
    discovery = paths["/api/local-events/review/discover-listings"]["post"]
    manual = paths["/api/local-events/review/listing-page"]["post"]
    listing_decision = paths["/api/local-events/review/listing-decision"]["post"]
    preview = paths["/api/local-events/review/preview-events"]["post"]
    collection = paths["/api/local-events/review/collect-events"]["post"]

    assert "preview-review-v1:" in listing_decision["description"]
    assert "REAL EVENT / NOT EVENT" in listing_decision["description"]
    assert "latest unexpired process-local server Preview manifest" in (
        listing_decision["description"]
    )
    assert "service restart, expiry, newer Preview" in listing_decision["description"]
    assert "manual re-add, or discovery retirement requires a new Preview" in (
        listing_decision["description"]
    )
    assert "prior Preview selection file is restored" in listing_decision["description"]
    assert "manifest remains available for retry" in listing_decision["description"]

    assert "one request-local Chromium process" in preview["description"]
    assert "--disable-http2" in preview["description"]
    assert "same browser lease" in preview["description"]
    assert "closed exactly once" in preview["description"]
    assert "fails instead of launching a second browser" in preview["description"]
    assert "preview_browser_process_count=1" in preview["description"]
    assert "preview_browser_reuse=listing_and_details" in preview["description"]
    assert "preview_detail_transport=single_http1_browser_process" in (
        preview["description"]
    )
    assert "process-local manifest" in preview["description"]
    assert "21,600-second lifetime" in preview["description"]
    assert "INFOSCREEN_PREVIEW_MANIFEST_TTL_SECONDS" in preview["description"]
    assert "does not change persisted Review state" in preview["description"]
    assert "browser-session drafts" in preview["description"]
    assert "must be Previewed again" in preview["description"]
    assert "browser-session" in preview["responses"]["500"]["description"]
    assert "final-detail invariant" in preview["responses"]["500"]["description"]

    assert "retired together with its committed Preview selection" in (
        discovery["description"]
    )
    assert "failed Review-state write restores" in discovery["description"]
    assert "removes its old committed Preview selection" in manual["description"]
    assert "process-local manifest" in manual["description"]

    assert collection["summary"] == (
        "Collect selected REAL EVENT candidates from confirmed pages"
    )
    assert "filters unselected listing cards before detail navigation" in collection["description"]
    assert "formal HTTP/1 Chromium policy" in collection["description"]
    assert "Preview transport policy" not in collection["description"]


def test_market_refresh_schema_contains_both_producer_outputs() -> None:
    payload = MarketRefreshResponse.model_validate(
        {
            "ok": True,
            "returncode": 0,
            "market": {"items": []},
            "weather": {"status": "OK"},
        }
    )

    assert payload.market == {"items": []}
    assert payload.weather == {"status": "OK"}


def test_pydantic_models_validate_closed_loop_fixture() -> None:
    root = Path(__file__).resolve().parent / "fixtures" / "runtime_data"
    local_events = LocalEventSearchResponse.model_validate_json((root / "local_event_search_results.json").read_text(encoding="utf-8"))
    photos = PhotosResponse.model_validate_json((root / "photos.json").read_text(encoding="utf-8"))
    assert local_events.ok is True
    assert local_events.count == len(local_events.results) == 1
    assert str(local_events.results[0].url).startswith("https://www.onepa.gov.sg/")
    assert photos.items[0].src == "/public_photos/fixture-photo.txt"


def test_market_config_request_rejects_empty_symbols() -> None:
    with pytest.raises(ValidationError):
        MarketConfigRequest(symbols=[])


def test_runtime_fixtures_are_valid_json() -> None:
    root = Path(__file__).resolve().parent / "fixtures" / "runtime_data"
    for path in root.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_public_photo_path_is_confined_to_public_directory(
    monkeypatch: pytest.MonkeyPatch,
    seeded_env: Path,
) -> None:
    monkeypatch.setattr(serve_infoscreen, "ENV_DIR", seeded_env)
    expected = (seeded_env / "public_photos" / "fixture-photo.txt").resolve()

    assert serve_infoscreen.public_photo_path("/public_photos/fixture-photo.txt") == expected

    unsafe_paths = [
        "/public_photos/../market.json",
        "/public_photos/%2e%2e/market.json",
        "/public_photos/%2E%2E%2Fmarket.json",
        "/public_photos/%2Fetc%2Fpasswd",
        "/public_photos/./fixture-photo.txt",
        "/public_photos/folder//fixture-photo.txt",
        "/public_photos/..%5cmarket.json",
        "/public_photos/%00fixture-photo.txt",
    ]
    for request_path in unsafe_paths:
        assert serve_infoscreen.public_photo_path(request_path) is None


def test_public_photo_path_rejects_symlink_escape(
    monkeypatch: pytest.MonkeyPatch,
    seeded_env: Path,
) -> None:
    monkeypatch.setattr(serve_infoscreen, "ENV_DIR", seeded_env)
    secret = seeded_env / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    link = seeded_env / "public_photos" / "escape.txt"
    try:
        link.symlink_to(secret)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert serve_infoscreen.public_photo_path("/public_photos/escape.txt") is None
