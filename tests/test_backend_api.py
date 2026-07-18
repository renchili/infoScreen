from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from surface import serve_infoscreen
from surface.api_models import (
    LocalEventSearchResponse,
    MarketConfigRequest,
    PhotosResponse,
    StudioRuleBindingRequest,
    StudioRuleImportRequest,
    StudioRuleRollbackRequest,
)
from surface.openapi_spec import build_openapi

pytestmark = pytest.mark.backend


def test_runtime_json_returns_fixture_payload(monkeypatch: pytest.MonkeyPatch, seeded_env: Path) -> None:
    monkeypatch.setattr(serve_infoscreen, "ENV_DIR", seeded_env)
    market = serve_infoscreen.runtime_json("market.json")
    assert market["source"] == "fixture-market"
    assert market["items"][0]["symbol"] == "AAPL"


def test_openapi_covers_dashboard_and_mutating_routes() -> None:
    spec = build_openapi()
    paths = spec["paths"]
    assert spec["openapi"].startswith("3.1")
    assert spec["servers"][0]["url"] == "http://127.0.0.1:8765"
    assert "/api/market-config" in paths
    assert "/api/market-refresh" in paths
    assert "/api/local-events/search" in paths
    assert "/public_photos/{path}" in paths

    studio_paths = {
        "/api/local-events/studio/sources": {"get"},
        "/api/local-events/studio/rules": {"get"},
        "/api/local-events/studio/draft": {"put", "delete"},
        "/api/local-events/studio/publish": {"post"},
        "/api/local-events/studio/rollback": {"post"},
        "/api/local-events/studio/import": {"post"},
        "/api/local-events/studio/export": {"get"},
    }
    for path, methods in studio_paths.items():
        assert path in paths
        assert methods <= set(paths[path])

    schemas = spec["components"]["schemas"]
    assert "LocalEventStudioRule" in schemas
    assert "StudioRuleListResponse" in schemas
    assert "StudioSourcesResponse" in schemas


def test_pydantic_models_validate_closed_loop_fixture() -> None:
    root = Path(__file__).resolve().parent / "fixtures" / "runtime_data"
    local_events = LocalEventSearchResponse.model_validate_json((root / "local_event_search_results.json").read_text(encoding="utf-8"))
    photos = PhotosResponse.model_validate_json((root / "photos.json").read_text(encoding="utf-8"))
    assert local_events.ok is True
    assert local_events.count == len(local_events.results) == 1
    assert str(local_events.results[0].url).startswith("https://www.onepa.gov.sg/")
    assert photos.items[0].src == "/public_photos/fixture-photo.txt"


def test_studio_request_models_reject_invalid_version_and_missing_rule() -> None:
    binding = StudioRuleBindingRequest(
        source_id="esplanade",
        listing_url="https://www.esplanade.com/whats-on",
    )
    assert binding.source_id == "esplanade"

    with pytest.raises(ValidationError):
        StudioRuleRollbackRequest(
            source_id="esplanade",
            listing_url="https://www.esplanade.com/whats-on",
            version=0,
        )

    with pytest.raises(ValidationError):
        StudioRuleImportRequest.model_validate({})


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
