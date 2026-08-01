from __future__ import annotations

from urllib.parse import urlparse

import pytest

from .conftest import RUNTIME_FIXTURES, read_json

pytestmark = pytest.mark.backend


def test_fixture_local_events_are_official_urls() -> None:
    data = read_json(RUNTIME_FIXTURES / "local_event_search_results.json")

    assert data["ok"] is True
    assert data["count"] == len(data["results"])
    for row in data["results"]:
        host = urlparse(row["url"]).netloc.lower()
        assert host.endswith("onepa.gov.sg")
        assert row["title"]
        assert row["when"]
        assert row["where"]
        assert row["source_name"]


def test_fixture_news_is_grouped_for_all_supported_languages() -> None:
    data = read_json(RUNTIME_FIXTURES / "event_stream.json")
    grouped = data["items_by_lang"]

    assert set(grouped) >= {"en", "fr", "zh"}
    assert all(grouped[key] for key in ["en", "fr", "zh"])
    assert grouped["zh"][0]["title"] == "中文测试标题"


def test_fixture_market_photo_schedule_weather_are_renderable() -> None:
    market = read_json(RUNTIME_FIXTURES / "market.json")
    photos = read_json(RUNTIME_FIXTURES / "photos.json")
    weather = read_json(RUNTIME_FIXTURES / "weather.json")
    schedule = read_json(RUNTIME_FIXTURES / "schedule.json")

    assert [item["symbol"] for item in market["items"]] == ["AAPL", "NVDA"]
    assert photos["items"][0]["src"].startswith("/public_photos/")
    assert isinstance(weather["temperature_c"], int)
    assert schedule[0]["title"] == "Fixture standup"
