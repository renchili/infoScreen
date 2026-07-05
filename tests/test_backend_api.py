from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from surface import serve_infoscreen
from surface.api_models import LocalEventSearchResponse, MarketConfigRequest, PhotosResponse
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
    assert "/api/market-config" in paths
    assert "/api/market-refresh" in paths
    assert "/api/local-events/search" in paths
    assert "/public_photos/{path}" in paths


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
