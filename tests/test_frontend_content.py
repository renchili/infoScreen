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


def test_local_event_frontend_orders_by_institution_then_result_order() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert "function sourceOrderMap" in js
    assert "row.source_order" in js
    assert "row.result_order" in js
    assert "a.sourceOrder - b.sourceOrder || a.resultOrder - b.resultOrder" in js


def test_frontend_references_closed_loop_runtime_files() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    for filename in ["schedule.json", "weather.json", "market.json", "event_stream.json", "photos.json"]:
        assert filename in js
