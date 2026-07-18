from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from surface.local_events_runtime.studio_capture import write_snapshot
from surface.local_events_runtime.studio_dom import SnapshotDom, StudioSelectorError, select_nodes
from surface.local_events_runtime.studio_evaluate import (
    StudioEvaluationError,
    evaluate_rule,
    require_publishable_test,
    test_draft as run_draft_test,
    validate_detail_url,
)
from surface.local_events_runtime.studio_rules import LocalEventStudioRule, LocalEventStudioRuleStore

pytestmark = pytest.mark.backend

PNG = b"\x89PNG\r\n\x1a\nfixture-png"
SNAPSHOT_ID = "20260719T040506123456Z-4183667b5e"
LISTING_URL = "https://www.esplanade.com/whats-on"


def source_config(tmp_path: Path) -> Path:
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
                        "listing_urls": [LISTING_URL],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def source_record() -> dict:
    return {
        "id": "esplanade",
        "name": "Esplanade",
        "allowed_domains": ["esplanade.com"],
        "default_venue": "Esplanade",
        "listing_urls": [LISTING_URL],
    }


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


def snapshot_dom() -> dict:
    return {
        "schema_version": 1,
        "page": {"document_width": 1440, "document_height": 2200},
        "candidate_count": 13,
        "element_count": 13,
        "truncated": False,
        "elements": [
            node("root", None, "main", "events-list"),
            node("card-1", "root", "article", "event-card"),
            node("title-1", "card-1", "h2", "event-title", "Future Music Session"),
            node("date-1", "card-1", "time", "event-date", "19 Jul 2099"),
            node("venue-1", "card-1", "div", "event-venue", "Esplanade Recital Studio"),
            node("link-1", "card-1", "a", "event-link", "Details", "https://www.esplanade.com/whats-on/festivals-and-series/future-music-session"),
            node("summary-1", "card-1", "p", "event-summary", "A real listed performance."),
            node("card-2", "root", "article", "event-card promo-card"),
            node("title-2", "card-2", "h2", "event-title", "Membership Promotion"),
            node("date-2", "card-2", "time", "event-date", "20 Jul 2099"),
            node("venue-2", "card-2", "div", "event-venue", "Online"),
            node("link-2", "card-2", "a", "event-link", "Details", "https://www.esplanade.com/membership"),
            node("summary-2", "card-2", "p", "event-summary", "Not an activity."),
        ],
    }


def draft_rule() -> LocalEventStudioRule:
    return LocalEventStudioRule.model_validate(
        {
            "schema_version": 1,
            "source_id": "esplanade",
            "listing_url": LISTING_URL,
            "version": 0,
            "status": "draft",
            "card": {
                "selector": "main.events-list > article.event-card",
                "exclude_selectors": ["article.promo-card"],
            },
            "fields": {
                "title": {"selector": "h2.event-title"},
                "when": {"selector": "time.event-date"},
                "where": {"selector": "div.event-venue", "allow_source_default": False},
                "url": {"selector": "a.event-link[href]", "attribute": "href"},
                "summary": {"selector": "p.event-summary", "optional": True},
            },
            "detail_page": {"enabled": False, "fields": {}},
            "validation": {
                "require_public_detail_url": True,
                "require_current_or_future_date": True,
            },
        }
    )


def write_fixture_snapshot(root: Path) -> None:
    write_snapshot(
        root,
        {
            "schema_version": 1,
            "snapshot_id": SNAPSHOT_ID,
            "source_id": "esplanade",
            "source_name": "Esplanade",
            "listing_url": LISTING_URL,
            "final_url": LISTING_URL,
            "page_title": "What's On",
            "captured_at": "2026-07-19T04:05:06.123456+00:00",
            "prepare": {},
            "dom_element_count": 13,
            "dom_truncated": False,
            "assets": {"screenshot": "page.png", "html": "page.html", "dom": "dom.json"},
        },
        screenshot=PNG,
        html="<html><body>fixture</body></html>",
        dom=snapshot_dom(),
    )


def test_snapshot_selector_engine_matches_child_descendant_attribute_and_nth() -> None:
    dom = SnapshotDom(snapshot_dom())
    assert [item["id"] for item in select_nodes(dom, "main.events-list > article.event-card")] == ["card-1", "card-2"]
    assert [item["id"] for item in select_nodes(dom, "article.event-card a.event-link[href]")] == ["link-1", "link-2"]
    assert [item["id"] for item in select_nodes(dom, "article.event-card:nth-of-type(2)")] == ["card-2"]
    assert [item["id"] for item in select_nodes(dom, "h2.event-title", within_id="card-1")] == ["title-1"]
    with pytest.raises(StudioSelectorError):
        select_nodes(dom, "article.event-card:first-child")


def test_evaluate_rule_accepts_only_listed_non_excluded_card_with_field_evidence() -> None:
    result = evaluate_rule(
        draft_rule(),
        snapshot_dom(),
        source_record(),
        today=date(2026, 7, 19),
    )
    assert result["matched_card_count"] == 2
    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert result["publishable"] is True
    accepted = result["accepted"][0]
    assert accepted["event"]["title"] == "Future Music Session"
    assert accepted["event"]["where"] == "Esplanade Recital Studio"
    assert accepted["event"]["url"].endswith("/future-music-session")
    assert accepted["event"]["candidate_policy"] == "studio-published-listing-v1"
    assert accepted["evidence"]["url"]["element_id"] == "link-1"
    assert accepted["evidence"]["where"]["precedence"] == "listing_mapped_field"
    assert result["rejected"][0]["reason"] == "excluded_by_rule"


def test_detail_url_validation_rejects_listing_external_internal_and_media_paths() -> None:
    source = source_record()
    cases = {
        LISTING_URL: "detail_url_is_listing",
        "https://evil.example/events/test": "detail_url_outside_allowed_domain",
        "https://www.esplanade.com/api/events/123": "detail_url_is_internal_endpoint",
        "https://www.esplanade.com/files/programme.pdf": "detail_url_is_media_or_document",
        "https://www.esplanade.com/whats-on#structured-1": "detail_url_is_synthetic",
    }
    for url, expected in cases.items():
        assert validate_detail_url(url, LISTING_URL, source)[1] == expected


def test_draft_test_persists_evidence_and_publish_gate_tracks_exact_fingerprint(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    config = source_config(tmp_path)
    write_fixture_snapshot(root)
    store = LocalEventStudioRuleStore(root=root, source_config_path=config)
    saved = store.save_draft(draft_rule())

    result = run_draft_test(
        "esplanade",
        LISTING_URL,
        SNAPSHOT_ID,
        root=root,
        source_config_path=config,
        today=date(2026, 7, 19),
    )
    assert result["publishable"] is True
    assert result["accepted_count"] == 1
    assert (root / "test-runs" / "esplanade" / f"{result['run_id']}.json").is_file()
    assert require_publishable_test(saved, root=root)["run_id"] == result["run_id"]

    changed = saved.model_copy(deep=True)
    changed.fields.title.selector = "h3.changed"
    with pytest.raises(StudioEvaluationError, match="changed after"):
        require_publishable_test(changed, root=root)


def test_non_publishable_zero_match_draft_is_recorded_but_cannot_publish(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    config = source_config(tmp_path)
    write_fixture_snapshot(root)
    store = LocalEventStudioRuleStore(root=root, source_config_path=config)
    raw = draft_rule().model_dump(mode="python")
    raw["card"]["selector"] = "article.no-such-card"
    saved = store.save_draft(raw)

    result = run_draft_test(
        "esplanade",
        LISTING_URL,
        SNAPSHOT_ID,
        root=root,
        source_config_path=config,
        today=date(2026, 7, 19),
    )
    assert result["publishable"] is False
    assert "card_selector_matched_zero_elements" in result["fatal_errors"]
    with pytest.raises(StudioEvaluationError, match="not publishable"):
        require_publishable_test(saved, root=root)
