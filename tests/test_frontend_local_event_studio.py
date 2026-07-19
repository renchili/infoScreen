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
        self.external_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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


def test_studio_page_uses_existing_static_asset_model() -> None:
    parser = parse_studio()
    assert parser.scripts == [
        "/assets/js/local_event_studio.js",
        "/assets/js/local_event_studio_test.js",
        "/assets/js/local_event_studio_run.js",
    ]
    assert parser.styles == [
        "/assets/css/local_event_studio.css",
        "/assets/css/local_event_studio_test.css",
        "/assets/css/local_event_studio_run.css",
    ]
    assert parser.external_assets == []


def test_studio_page_contains_complete_local_workflow_controls() -> None:
    parser = parse_studio()
    required = {
        "workflow-state",
        "source-select",
        "listing-select",
        "snapshot-select",
        "capture-button",
        "reload-button",
        "page-image",
        "annotation-canvas",
        "card-selector",
        "exclude-selectors",
        "field-editor",
        "allow-source-default",
        "detail-enabled",
        "detail-fields",
        "save-draft-button",
        "test-draft-button",
        "publish-button",
        "export-button",
        "import-input",
        "history-select",
        "rollback-button",
        "field-evidence",
        "test-state",
        "test-result",
        "test-matched",
        "test-accepted",
        "test-rejected",
        "test-publishable",
        "accepted-preview",
        "rejected-preview",
        "production-status",
        "production-location",
        "run-local-events-button",
        "production-count",
        "production-partial",
        "production-completed",
        "production-incomplete",
        "production-message",
        "production-results",
    }
    assert required.issubset(parser.ids)


def test_studio_javascript_uses_only_existing_8765_relative_apis() -> None:
    editor_js = read_text("surface/web/assets/js/local_event_studio.js")
    test_js = read_text("surface/web/assets/js/local_event_studio_test.js")
    run_js = read_text("surface/web/assets/js/local_event_studio_run.js")
    combined = editor_js + "\n" + test_js + "\n" + run_js
    for path in [
        "/api/local-events/studio/sources",
        "/api/local-events/studio/rules",
        "/api/local-events/studio/snapshots",
        "/api/local-events/studio/snapshot-asset",
        "/api/local-events/studio/capture",
        "/api/local-events/studio/draft",
        "/api/local-events/studio/test",
        "/api/local-events/studio/test-latest",
        "/api/local-events/studio/publish",
        "/api/local-events/studio/rollback",
        "/api/local-events/studio/import",
        "/api/local-events/studio/export",
        "/api/local-events/search",
    ]:
        assert path in combined
    assert "8766" not in combined
    assert "http://127.0.0.1" not in combined
    assert "https://127.0.0.1" not in combined
    assert "React" not in combined


def test_studio_annotation_maps_dom_selectors_not_coordinate_rules() -> None:
    js = read_text("surface/web/assets/js/local_event_studio.js")
    assert "function relativeSelector" in js
    assert "function inferCardSelector" in js
    assert "data-infoscreen-studio-id" not in js
    assert "payload.card" in js
    assert "payload.fields" in js
    assert "regions" not in js
    assert "x_percent" not in js
    assert "y_percent" not in js


def test_studio_test_preview_requires_server_publishability() -> None:
    js = read_text("surface/web/assets/js/local_event_studio_test.js")
    assert "result.publishable" in js
    assert "result.run_id" in js
    assert "PUBLISH TESTED DRAFT" in read_text("surface/web/local-events/studio/index.html")
    assert 'event.stopImmediatePropagation()' in js
    assert 'ui.publishButton.addEventListener("click", publishTestedDraft, true);' in js


def test_studio_waits_for_initial_source_binding_before_latest_test_lookup() -> None:
    js = read_text("surface/web/assets/js/local_event_studio_test.js")
    assert "async function loadLatestWhenBindingReady" in js
    assert "attempt >= 50" in js
    assert "loadLatestWhenBindingReady(attempt + 1)" in js
    assert "setTimeout(() => loadLatestWhenBindingReady()" in js


def test_studio_exposes_loading_empty_error_and_retry_interactions() -> None:
    html = read_text("surface/web/local-events/studio/index.html")
    js = read_text("surface/web/assets/js/local_event_studio.js")
    run_js = read_text("surface/web/assets/js/local_event_studio_run.js")
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert "No snapshots captured" in js
    assert "setStatus(error.message" in js
    assert "reload-button" in html
    assert "CAPTURE NOW" in html
    assert "RUNNING · MAY TAKE SEVERAL MINUTES" in run_js
    assert "No production activities are present" in run_js
    assert "RUN LOCAL EVENTS NOW" in html


def test_studio_production_workflow_runs_existing_local_events_endpoint_and_renders_fields() -> None:
    html = read_text("surface/web/local-events/studio/index.html")
    js = read_text("surface/web/assets/js/local_event_studio_run.js")
    assert "CAPTURE" in html
    assert "CARDS" in html
    assert "FIELDS" in html
    assert "TEST" in html
    assert "PUBLISH" in html
    assert "RUN" in html
    assert 'method: "POST"' in js
    assert 'body: JSON.stringify({ location })' in js
    assert 'requestJson("/api/local-events/search"' in js
    assert 'appendDefinition(values, "WHEN", event.when)' in js
    assert 'appendDefinition(values, "WHERE", event.where)' in js
    assert 'appendDefinition(values, "POLICY", event.candidate_policy)' in js
    assert 'window.localStorage.setItem("local_events_location", location)' in js
