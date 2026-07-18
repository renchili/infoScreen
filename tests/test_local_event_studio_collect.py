from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from surface.local_events_runtime.studio_collect import (
    apply_published_studio_rules,
    collect_published_source,
)
from surface.local_events_runtime.studio_rules import LocalEventStudioRuleStore

pytestmark = pytest.mark.backend

LISTING_URL = "https://www.esplanade.com/whats-on"
DETAIL_URL = "https://www.esplanade.com/whats-on/festivals-and-series/future-music-session"


def node(
    node_id: str,
    parent_id: str | None,
    tag: str,
    classes: str = "",
    text: str = "",
    href: str = "",
) -> dict:
    attributes = {"class": classes} if classes else {}
    if href:
        attributes["href"] = href
    return {
        "id": node_id,
        "parent_id": parent_id,
        "tag": tag,
        "selector": tag,
        "text": text,
        "href": href,
        "src": "",
        "attributes": attributes,
        "rect": {"x": 0, "y": 0, "width": 100, "height": 20},
    }


def listing_dom() -> dict:
    elements = [
        node("root", None, "main", "events-list"),
        node("card", "root", "article", "event-card"),
        node("title", "card", "h2", "event-title", "Future Music Session"),
        node("date", "card", "time", "event-date", "19 Jul 2099"),
        node("venue", "card", "div", "event-venue", "Esplanade"),
        node("link", "card", "a", "event-link", "Details", DETAIL_URL),
        node("summary", "card", "p", "event-summary", "Listing summary."),
    ]
    return {
        "schema_version": 1,
        "page": {"document_width": 1440, "document_height": 2200},
        "candidate_count": len(elements),
        "element_count": len(elements),
        "truncated": False,
        "elements": elements,
    }


def detail_dom() -> dict:
    elements = [
        node("detail-root", None, "main", "event-detail"),
        node("detail-title", "detail-root", "h1", "detail-title", "Future Music Session"),
        node("detail-date", "detail-root", "div", "detail-date", "20 Jul 2099, 7:30 PM"),
        node("detail-venue", "detail-root", "div", "detail-venue", "Esplanade Recital Studio"),
        node("detail-summary", "detail-root", "p", "detail-summary", "Authoritative detail summary."),
    ]
    return {
        "schema_version": 1,
        "page": {"document_width": 1440, "document_height": 1200},
        "candidate_count": len(elements),
        "element_count": len(elements),
        "truncated": False,
        "elements": elements,
    }


def source_config(tmp_path: Path, *, extra_listing: bool = False) -> Path:
    listings = [LISTING_URL]
    if extra_listing:
        listings.append("https://www.esplanade.com/whats-on/free-programmes")
    path = tmp_path / "event_sources.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "esplanade",
                        "name": "Esplanade",
                        "allowed_domains": ["esplanade.com"],
                        "default_venue": "Esplanade",
                        "listing_urls": listings,
                    },
                    {
                        "id": "onepa",
                        "name": "onePA / People's Association",
                        "allowed_domains": ["onepa.gov.sg"],
                        "default_venue": "People's Association CCs",
                        "listing_urls": ["https://www.onepa.gov.sg/events"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def draft_payload(*, detail_enabled: bool = True) -> dict:
    return {
        "schema_version": 1,
        "source_id": "esplanade",
        "listing_url": LISTING_URL,
        "version": 0,
        "status": "draft",
        "card": {"selector": "main.events-list > article.event-card", "exclude_selectors": []},
        "fields": {
            "title": {"selector": "h2.event-title"},
            "when": {"selector": "time.event-date"},
            "where": {"selector": "div.event-venue", "allow_source_default": False},
            "url": {"selector": "a.event-link[href]", "attribute": "href"},
            "summary": {"selector": "p.event-summary", "optional": True},
        },
        "detail_page": {
            "enabled": detail_enabled,
            "fields": {
                "title": {"selector": "h1.detail-title"},
                "when": {"selector": "div.detail-date"},
                "where": {"selector": "div.detail-venue", "allow_source_default": False},
                "summary": {"selector": "p.detail-summary", "optional": True},
            } if detail_enabled else {},
        },
        "validation": {"require_public_detail_url": True, "require_current_or_future_date": True},
    }


def publish_rule(root: Path, config: Path, *, detail_enabled: bool = True):
    store = LocalEventStudioRuleStore(root=root, source_config_path=config)
    store.save_draft(draft_payload(detail_enabled=detail_enabled))
    return store.publish("esplanade", LISTING_URL)


class FakeBrowser:
    def __init__(self, *, fail_listing: bool = False) -> None:
        self.fail_listing = fail_listing
        self.detail_calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def render_listing(self, source: dict, listing_url: str) -> dict:
        if self.fail_listing:
            raise RuntimeError("fixture listing failure")
        assert source["id"] == "esplanade"
        assert listing_url == LISTING_URL
        return {
            "final_url": LISTING_URL,
            "page_title": "What's On",
            "prepare": {"clicks": 1},
            "dom": listing_dom(),
        }

    def render_detail(self, source: dict, detail_url: str) -> dict:
        self.detail_calls.append(detail_url)
        return {
            "final_url": detail_url,
            "page_title": "Future Music Session",
            "dom": detail_dom(),
        }


def base_payload() -> dict:
    return {
        "count": 2,
        "results": [
            {
                "title": "Wrong Legacy Esplanade Row",
                "source_name": "Esplanade",
                "host": "Esplanade",
                "url": "https://www.esplanade.com/whats-on",
                "listing_url": LISTING_URL,
            },
            {
                "title": "Existing onePA Event",
                "source_name": "onePA / People's Association",
                "host": "onePA / People's Association",
                "url": "https://www.onepa.gov.sg/events/fixture",
                "listing_url": "https://www.onepa.gov.sg/events",
            },
        ],
        "debug_by_source": [
            {"source": "Esplanade", "status": "complete", "accepted": 1},
            {"source": "onePA / People's Association", "status": "complete", "accepted": 1},
        ],
    }


def test_collect_published_source_uses_detail_fields_and_rule_evidence(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    rule = publish_rule(tmp_path / "studio", config)
    browser = FakeBrowser()
    results, debug = collect_published_source(
        json.loads(config.read_text(encoding="utf-8"))["sources"][0],
        [rule],
        browser_factory=lambda: browser,
        today=date(2026, 7, 19),
    )

    assert len(results) == 1
    event = results[0]
    assert event["title"] == "Future Music Session"
    assert event["when"] == "20 Jul 2099, 7:30 PM"
    assert event["where"] == "Esplanade Recital Studio"
    assert event["summary"] == "Authoritative detail summary."
    assert event["url"] == DETAIL_URL
    assert event["candidate_policy"] == "official-listing-authority-v1"
    assert event["source_type"] == "studio_published_rule"
    assert event["studio_rule_version"] == 1
    assert event["studio_evidence"]["where"]["page_role"] == "detail"
    assert browser.detail_calls == [DETAIL_URL]
    assert debug[0]["accepted"] == 1
    assert debug[0]["status"] == "complete"


def test_full_source_activation_replaces_legacy_source_and_preserves_others(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    root = tmp_path / "studio"
    publish_rule(root, config, detail_enabled=False)

    output = apply_published_studio_rules(
        base_payload(),
        root=root,
        source_config_path=config,
        browser_factory=FakeBrowser,
        today=date(2026, 7, 19),
    )

    assert [item["title"] for item in output["results"]] == [
        "Existing onePA Event",
        "Future Music Session",
    ]
    assert output["count"] == 2
    assert [row["source"] for row in output["debug_by_source"]] == [
        "onePA / People's Association",
        "Esplanade",
    ]
    assert output["studio_activations"][0]["full_source_activation"] is True


def test_partial_listing_activation_removes_only_legacy_rows_with_matching_listing(tmp_path: Path) -> None:
    config = source_config(tmp_path, extra_listing=True)
    root = tmp_path / "studio"
    publish_rule(root, config, detail_enabled=False)
    payload = base_payload()
    payload["results"].insert(
        1,
        {
            "title": "Legacy Free Programme",
            "source_name": "Esplanade",
            "host": "Esplanade",
            "url": "https://www.esplanade.com/whats-on/free-programmes/fixture",
            "listing_url": "https://www.esplanade.com/whats-on/free-programmes",
        },
    )

    output = apply_published_studio_rules(
        payload,
        root=root,
        source_config_path=config,
        browser_factory=FakeBrowser,
        today=date(2026, 7, 19),
    )
    titles = [item["title"] for item in output["results"]]
    assert "Wrong Legacy Esplanade Row" not in titles
    assert "Legacy Free Programme" in titles
    assert "Existing onePA Event" in titles
    assert "Future Music Session" in titles
    assert output["studio_activations"][0]["full_source_activation"] is False


def test_studio_failure_marks_partial_without_erasing_unrelated_source(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    root = tmp_path / "studio"
    publish_rule(root, config, detail_enabled=False)

    output = apply_published_studio_rules(
        base_payload(),
        root=root,
        source_config_path=config,
        browser_factory=lambda: FakeBrowser(fail_listing=True),
        today=date(2026, 7, 19),
    )
    assert [item["title"] for item in output["results"]] == ["Existing onePA Event"]
    assert output["partial"] is True
    studio_debug = next(row for row in output["debug_by_source"] if row.get("adapter") == "studio_published_rule")
    assert studio_debug["source"] == "Esplanade"
    assert studio_debug["complete"] is False
    assert studio_debug["status"] == "failed"


def test_payload_is_unchanged_when_no_published_rules_exist(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    payload = base_payload()
    assert apply_published_studio_rules(
        payload,
        root=tmp_path / "studio",
        source_config_path=config,
        browser_factory=FakeBrowser,
    ) == payload
