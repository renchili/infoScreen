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
    StudioCaptureRequest,
    StudioRuleBindingRequest,
    StudioRuleImportRequest,
    StudioRuleRollbackRequest,
    StudioSnapshotMetadata,
    StudioTestRequest,
    StudioTestResult,
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
        "/api/local-events/studio/test": {"post"},
        "/api/local-events/studio/test-latest": {"get"},
        "/api/local-events/studio/publish": {"post"},
        "/api/local-events/studio/rollback": {"post"},
        "/api/local-events/studio/import": {"post"},
        "/api/local-events/studio/export": {"get"},
        "/api/local-events/studio/capture": {"post"},
        "/api/local-events/studio/snapshots": {"get"},
        "/api/local-events/studio/snapshot-asset": {"get"},
    }
    for path, methods in studio_paths.items():
        assert path in paths
        assert methods <= set(paths[path])

    schemas = spec["components"]["schemas"]
    for name in [
        "LocalEventStudioRule",
        "StudioRuleListResponse",
        "StudioSourcesResponse",
        "StudioCaptureRequest",
        "StudioSnapshotMetadata",
        "StudioSnapshotListResponse",
        "StudioTestRequest",
        "StudioTestResult",
        "StudioTestResponse",
        "StudioLatestTestResponse",
    ]:
        assert name in schemas


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
    capture = StudioCaptureRequest.model_validate(binding.model_dump())
    assert capture.source_id == "esplanade"

    test_request = StudioTestRequest(
        **binding.model_dump(),
        snapshot_id="20260719T040506123456Z-4183667b5e",
    )
    assert test_request.snapshot_id.endswith("4183667b5e")

    with pytest.raises(ValidationError):
        StudioRuleRollbackRequest(
            source_id="esplanade",
            listing_url="https://www.esplanade.com/whats-on",
            version=0,
        )

    with pytest.raises(ValidationError):
        StudioRuleImportRequest.model_validate({})

    with pytest.raises(ValidationError):
        StudioTestRequest(
            **binding.model_dump(),
            snapshot_id="",
        )

    snapshot = StudioSnapshotMetadata.model_validate(
        {
            "schema_version": 1,
            "snapshot_id": "20260719T040506123456Z-4183667b5e",
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
            "final_url": "https://www.esplanade.com/whats-on",
            "captured_at": "2026-07-19T04:05:06.123456+00:00",
        }
    )
    assert snapshot.dom_element_count == 0

    result = StudioTestResult.model_validate(
        {
            "schema_version": 1,
            "run_id": "20260719T040506123456Z-fixture",
            "snapshot_id": snapshot.snapshot_id,
            "tested_at": snapshot.captured_at,
            "rule_fingerprint": "a" * 64,
            "source_id": "esplanade",
            "listing_url": "https://www.esplanade.com/whats-on",
            "matched_card_count": 1,
            "accepted_count": 1,
            "rejected_count": 0,
            "publishable": True,
            "accepted": [
                {
                    "card_id": "card-1",
                    "event": {
                        "title": "Fixture event",
                        "when": "19 Jul 2099",
                        "where": "Esplanade",
                        "url": "https://www.esplanade.com/whats-on/fixture-event",
                    },
                    "evidence": {},
                }
            ],
        }
    )
    assert result.publishable is True
    assert result.accepted_count == len(result.accepted) == 1


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
