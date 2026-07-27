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
from surface.local_events_runtime.event_review import (
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
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
    assert "/api/local-events/review/preview-events" in paths
    assert "/public_photos/{path}" in paths

    assert "404" not in paths["/api/local-events/search"]["get"]["responses"]
    assert "404" not in paths["/local_event_search_results.json"]["get"]["responses"]
    assert "504" in paths["/api/local-events/search"]["post"]["responses"]
    assert "sanitized" not in paths["/"]["get"]["description"].lower()

    preview = paths["/api/local-events/review/preview-events"]["post"]
    schema = preview["requestBody"]["content"]["application/json"]["schema"]
    assert schema["required"] == ["listing_url"]
    assert schema["properties"]["listing_url"]["format"] == "uri"
    assert "temporary" in preview["description"].lower()
    assert "real list-page decision" in preview["description"]
    assert set(preview["responses"]) == {"200", "400", "500"}


def test_preview_event_candidates_uses_temporary_state_without_mutating_real_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "review", config)
    pending_url = "https://example.test/events/pending"
    confirmed_url = "https://example.test/events/confirmed"
    original = ReviewState(
        listing_pages=[
            ListingPageCandidate(
                candidate_id="pending-page",
                source_id="source",
                source_name="Source",
                url=pending_url,
                origin="discovered",
                decision="pending",
                discovered_at="2026-07-28T00:00:00+00:00",
            ),
            ListingPageCandidate(
                candidate_id="confirmed-page",
                source_id="source",
                source_name="Source",
                url=confirmed_url,
                origin="configured",
                decision="confirmed",
                discovered_at="2026-07-28T00:00:00+00:00",
            ),
        ],
        listing_collection={"preserved_in_real_state": True},
        event_collection={"previous_real_collection": True},
    )
    store.save(original)
    real_state_before = store.state_path.read_bytes()
    captured: dict[str, object] = {}

    def fake_collect(temporary_store: EventReviewStore) -> ReviewState:
        captured["root"] = temporary_store.root
        captured["state"] = temporary_store.load()
        return temporary_store.load()

    monkeypatch.setattr(serve_infoscreen, "collect_event_candidates", fake_collect)
    preview = serve_infoscreen.preview_event_candidates(store, pending_url)

    temporary_state = captured["state"]
    assert isinstance(temporary_state, ReviewState)
    assert [item.url for item in temporary_state.listing_pages] == [pending_url]
    assert temporary_state.listing_pages[0].decision == "confirmed"
    assert temporary_state.events == []
    assert temporary_state.feedback == []
    assert temporary_state.event_collection == {}
    assert preview.model_dump(mode="json") == temporary_state.model_dump(mode="json")

    assert store.state_path.read_bytes() == real_state_before
    assert store.load().model_dump(mode="json") == original.model_dump(mode="json")
    temporary_root = captured["root"]
    assert isinstance(temporary_root, Path)
    assert temporary_root != store.root
    assert not temporary_root.exists()


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
