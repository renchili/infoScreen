from __future__ import annotations

import pytest

from surface import fetch_event_stream
from .conftest import read_text

pytestmark = pytest.mark.backend


def test_news_pool_places_singapore_sources_before_random_remainder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fetch_event_stream.random, "shuffle", lambda rows: None)
    rows = [
        {"base_source": "France24", "base_title": "World"},
        {"base_source": "CNA", "base_title": "Singapore"},
        {"base_source": "BBC中文", "base_title": "World zh"},
        {"base_source": "新加坡", "base_title": "Singapore zh"},
    ]

    prioritized = fetch_event_stream.prioritized_pool(rows)

    assert [row["base_source"] for row in prioritized[:2]] == ["CNA", "新加坡"]
    assert [row["base_source"] for row in prioritized[2:]] == ["France24", "BBC中文"]


def test_runtime_producers_use_atomic_file_replacement() -> None:
    live = read_text("surface/fetch_live_data.py")
    news = read_text("surface/fetch_event_stream.py")
    photos = read_text("surface/build_photos_json.py")

    for source in [live, news, photos]:
        assert "def atomic_write_json" in source
        assert "os.replace(temporary, path)" in source

    assert "atomic_write_json(WEATHER, payload)" in live
    assert "atomic_write_json(MARKET, payload)" in live
    assert "atomic_write_json(OUT, payload)" in news
    assert "atomic_write_json(OUT_JSON, payload)" in photos


def test_live_data_failure_records_attempt_and_fails_the_service() -> None:
    live = read_text("surface/fetch_live_data.py")

    assert 'def log(component: str, state: str, **fields) -> None:' in live
    assert 'payload["last_attempt_at"] = attempt_at' in live
    assert 'payload["last_success_at"] = payload.get("updated_at") or attempt_at' in live
    assert '"status": "ERR"' in live
    assert 'retained_updated_at=payload.get("updated_at")' in live
    assert '"live-data",\n        "failure",' in live
    assert "raise SystemExit(1)" in live
