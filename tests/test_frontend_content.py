from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

from .conftest import ROOT, read_text

pytestmark = pytest.mark.frontend


class IdAndAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(str(data["id"]))
        if tag == "script" and data.get("src"):
            self.scripts.append(str(data["src"]))
        if tag == "link" and data.get("rel") == "stylesheet" and data.get("href"):
            self.styles.append(str(data["href"]))

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.text.append(stripped)


def parse_index() -> IdAndAssetParser:
    parser = IdAndAssetParser()
    parser.feed(read_text("surface/web/index.html"))
    return parser


def test_index_loads_only_asset_directory_scripts_and_styles() -> None:
    parser = parse_index()

    assert parser.scripts == [
        "assets/js/dashboard.js",
        "assets/js/calendar_board.js",
        "assets/js/local_event_card.js",
        "assets/js/market_custom.js",
    ]
    assert parser.styles == [
        "assets/css/app.css",
        "assets/css/calendar_board.css",
        "assets/css/local_events.css",
        "assets/css/market_custom.css",
    ]
    assert not list((ROOT / "surface" / "web").glob("*.js"))
    assert not list((ROOT / "surface" / "web").glob("*.css"))


def test_index_contains_required_dashboard_mount_points() -> None:
    parser = parse_index()
    required = {
        "globalMarketTapeTrack",
        "marketList",
        "localEventList",
        "localEventCounter",
        "localEventPrevButton",
        "localEventNextButton",
        "localEventLocationButton",
        "localEventInstitutionSelect",
        "localEventFilterInput",
        "localEventSearchButton",
        "leftSyncTapeTrack",
        "newsTickerTrackEN",
        "newsTickerTrackFR",
        "newsTickerTrackZH",
        "photoFlipWall",
        "weatherTemp",
        "agendaList",
    }

    assert required.issubset(parser.ids)


def test_index_photo_empty_state_uses_runtime_photo_path() -> None:
    html = read_text("surface/web/index.html")

    assert "~/infoscreen/surface/.env/photos" in html
    assert "~/infoscreen/photos" not in html


def test_local_event_frontend_uses_official_link_and_escape_contract() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert 'var API = "/api/local-events/search"' in js
    assert 'rel="noopener noreferrer"' in js
    assert "OPEN OFFICIAL LINK" in js
    assert "function esc" in js
    assert "items_by_lang" in js
    assert 'method: "HEAD"' in js


def test_dashboard_local_event_search_filters_current_runtime_only() -> None:
    html = read_text("surface/web/index.html")
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert "Filter local events" in html
    assert "All institutions" in html
    assert "Keyword, date or place" in html
    assert "function populateInstitutionFilter()" in js
    assert "function applyFilters(preserveCurrent)" in js
    assert 'localStorage.getItem("local_events_filter_source")' in js
    assert 'localStorage.getItem("local_events_filter_query")' in js
    assert 'pick(row, ["source_name", "institution"' in js
    assert 'fetch(API, { method: "POST"' not in js
    assert 'body: JSON.stringify({ location:' not in js
    assert 'fetch(API, { cache: "no-store" })' in js


def test_calendar_board_reloads_schedule_without_page_reload() -> None:
    js = read_text("surface/web/assets/js/calendar_board.js")

    assert "var ROTATE_INTERVAL_MS = 7000;" in js
    assert "var RELOAD_INTERVAL_MS = 60000;" in js
    assert "rotateTimer = setInterval(rotate, ROTATE_INTERVAL_MS)" in js
    assert "reloadTimer = setInterval(load, RELOAD_INTERVAL_MS)" in js
    assert "if (loading) return;" in js
    assert "function sameItems(nextItems)" in js
    assert 'fetch("schedule.json?_=" + Date.now(), { cache: "no-store" })' in js
    assert "window.location.reload" not in js


def test_market_rendering_has_one_owner() -> None:
    dashboard = read_text("surface/web/assets/js/dashboard.js")
    local_event = read_text("surface/web/assets/js/local_event_card.js")
    market_custom = read_text("surface/web/assets/js/market_custom.js")

    assert "async function loadMarket()" in dashboard
    assert 'id("marketList")' in dashboard
    assert 'id("globalMarketTapeTrack")' in dashboard
    assert "window.loadMarket = loadMarket" in dashboard

    assert "repairMarket" not in local_event
    assert 'el("marketList")' not in local_event
    assert 'el("globalMarketTapeTrack")' not in local_event
    assert 'fetch("market.json' not in local_event

    assert "window.loadMarket" in market_custom
    assert 'byId("marketList")' in market_custom
    assert "list.innerHTML" not in market_custom
    assert "globalMarketTapeTrack" not in market_custom
    assert 'fetch("market.json' not in market_custom


def test_news_and_sync_ticker_have_one_owner() -> None:
    dashboard = read_text("surface/web/assets/js/dashboard.js")
    local_event = read_text("surface/web/assets/js/local_event_card.js")

    assert "loadEventStream" not in dashboard
    assert "loadSyncTape" not in dashboard
    assert "newsTickerTrackEN" not in dashboard
    assert "leftSyncTapeTrack" not in dashboard

    assert "function repairNews()" in local_event
    assert "function loadSyncStatus()" in local_event
    assert 'el("newsTickerTrackEN")' in local_event
    assert 'el("leftSyncTapeTrack")' in local_event


def test_demo_metrics_are_explicit_in_source() -> None:
    dashboard = read_text("surface/web/assets/js/dashboard.js")

    assert "function updateDemoMetrics()" in dashboard
    assert "Math.random()" in dashboard
    assert "updateMetrics" not in dashboard


def test_frontend_references_closed_loop_runtime_files() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    for filename in ["schedule.json", "weather.json", "market.json", "event_stream.json", "photos.json"]:
        assert filename in js
