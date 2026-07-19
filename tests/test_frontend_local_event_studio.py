from __future__ import annotations

from html.parser import HTMLParser

import pytest

from .conftest import read_text

pytestmark = pytest.mark.frontend


class StudioParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.tags: list[str] = []
        self.external_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(str(data["id"]))
        if tag == "script" and data.get("src"):
            source = str(data["src"])
            self.scripts.append(source)
            if source.startswith(("http://", "https://", "//")):
                self.external_assets.append(source)
        if tag == "link" and data.get("href"):
            source = str(data["href"])
            self.styles.append(source)
            if source.startswith(("http://", "https://", "//")):
                self.external_assets.append(source)


def parse_studio() -> StudioParser:
    parser = StudioParser()
    parser.feed(read_text("surface/web/local-events/studio/index.html"))
    return parser


def test_studio_page_uses_one_existing_static_asset_pair() -> None:
    parser = parse_studio()
    assert parser.scripts == ["/assets/js/local_event_studio.js"]
    assert parser.styles == ["/assets/css/local_event_studio.css"]
    assert parser.external_assets == []


def test_studio_page_contains_live_browser_workflow_controls() -> None:
    parser = parse_studio()
    required = {
        "global-status",
        "source-select",
        "listing-select",
        "open-browser",
        "reload-state",
        "browser-message",
        "rule-status",
        "card-selector",
        "url-selector",
        "listing-fields",
        "detail-fields",
        "listing-actions",
        "detail-actions",
        "test-status",
        "matched",
        "accepted",
        "rejected",
        "publishable",
        "accepted-list",
        "rejected-list",
        "publish",
        "run-status",
        "location",
        "run",
        "run-message",
        "results",
    }
    assert required.issubset(parser.ids)


def test_studio_does_not_embed_or_annotate_a_screenshot() -> None:
    parser = parse_studio()
    html = read_text("surface/web/local-events/studio/index.html")
    assert "iframe" not in parser.tags
    assert "canvas" not in parser.tags
    assert "page-image" not in parser.ids
    assert "annotation-canvas" not in parser.ids
    assert "No iframe and no screenshot clicking" in html
    assert "OPEN REAL BROWSER" in html


def test_studio_javascript_uses_only_existing_8765_relative_apis() -> None:
    js = read_text("surface/web/assets/js/local_event_studio.js")
    for path in [
        "/api/local-events/studio/sources",
        "/api/local-events/studio/rules",
        "/api/local-events/studio/capture",
        "/api/local-events/studio/test-latest",
        "/api/local-events/studio/publish",
        "/api/local-events/search",
    ]:
        assert path in js
    assert "8766" not in js
    assert "http://127.0.0.1" not in js
    assert "https://127.0.0.1" not in js


def test_live_browser_worker_uses_real_dom_and_every_detail_page() -> None:
    worker = read_text("surface/local_events_runtime/studio_live.py")
    assert "launch_persistent_context" in worker
    assert "headless=False" in worker
    assert "context.expose_binding" in worker
    assert "DOM_EVIDENCE_JS" in worker
    assert "_goto_detail(detail, public_url)" in worker
    assert "execute_browser_actions(detail, rule.detail_actions)" in worker
    assert "live_validation_requires_two_confirmed_detail_pages" in worker
    assert "window.__infoscreenCardSelector" in worker


def test_live_overlay_records_interactions_on_real_dom() -> None:
    overlay = read_text("surface/local_events_runtime/studio_live_overlay.py")
    for value in [
        "RECORD CLICK",
        "REPEAT CLICK",
        "RECORD SELECT",
        "RECORD SCROLL BOTTOM",
        "RECORD WAIT",
        "LIST CARD",
        "DETAIL LINK",
    ]:
        assert value in overlay
    assert "currentRole" in overlay
    assert "uniqueSelector" in overlay
    assert "relativeSelector" in overlay
    assert "iframe" not in overlay


def test_live_production_collector_replays_actions_and_reads_details() -> None:
    collector = read_text("surface/local_events_runtime/studio_live_collect.py")
    assert "execute_browser_actions" in collector
    assert "page.locator(rule.card.selector)" in collector
    assert "validate_detail_url" in collector
    assert "_collect_detail" in collector
    assert 'for name in ("title", "when", "where")' in collector
    assert '"candidate_policy": "official-listing-authority-v1"' in collector
    assert '"source_type": "studio_live_rule"' in collector


def test_studio_exposes_failure_retry_and_stale_test_states() -> None:
    html = read_text("surface/web/local-events/studio/index.html")
    js = read_text("surface/web/assets/js/local_event_studio.js")
    assert "RELOAD STATE" in html
    assert "VALIDATION FAILED" in js
    assert "DRAFT CHANGED AFTER VALIDATION" in js
    assert "BROWSER START FAILED" in js
    assert "RUN LOCAL EVENTS NOW" in html
    assert "RUNNING" in js
