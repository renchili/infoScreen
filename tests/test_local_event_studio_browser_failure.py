from __future__ import annotations

import json
from pathlib import Path

import pytest

from surface.local_events_runtime.studio_collect import apply_published_studio_rules
from surface.local_events_runtime.studio_rules import LocalEventStudioRuleStore

pytestmark = pytest.mark.backend

LISTING_URL = "https://www.esplanade.com/whats-on"


class BrowserStartupFailure:
    def __enter__(self):
        raise RuntimeError("fixture browser startup failure")

    def __exit__(self, exc_type, exc, traceback):
        return None


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


def publish_esplanade_rule(root: Path, config: Path) -> None:
    store = LocalEventStudioRuleStore(root=root, source_config_path=config)
    store.save_draft(
        {
            "schema_version": 1,
            "source_id": "esplanade",
            "listing_url": LISTING_URL,
            "version": 0,
            "status": "draft",
            "card": {"selector": "article.event-card", "exclude_selectors": []},
            "fields": {
                "title": {"selector": "h2.event-title"},
                "when": {"selector": "time.event-date"},
                "where": {"selector": ".event-venue", "allow_source_default": False},
                "url": {"selector": "a.event-link[href]", "attribute": "href"},
            },
            "detail_page": {"enabled": False, "fields": {}},
            "validation": {
                "require_public_detail_url": True,
                "require_current_or_future_date": True,
            },
        }
    )
    store.publish("esplanade", LISTING_URL)


def test_browser_startup_failure_marks_only_studio_source_partial(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    root = tmp_path / "studio"
    publish_esplanade_rule(root, config)
    payload = {
        "source_count": 2,
        "count": 2,
        "results": [
            {
                "title": "Legacy Esplanade row",
                "source_name": "Esplanade",
                "host": "Esplanade",
                "listing_url": LISTING_URL,
                "url": "https://www.esplanade.com/whats-on/legacy-row",
            },
            {
                "title": "Existing onePA event",
                "source_name": "onePA / People's Association",
                "host": "onePA / People's Association",
                "listing_url": "https://www.onepa.gov.sg/events",
                "url": "https://www.onepa.gov.sg/events/existing-event",
            },
        ],
        "debug_by_source": [
            {"source": "Esplanade", "complete": True, "accepted": 1},
            {"source": "onePA / People's Association", "complete": True, "accepted": 1},
        ],
    }

    output = apply_published_studio_rules(
        payload,
        root=root,
        source_config_path=config,
        browser_factory=BrowserStartupFailure,
    )

    assert [item["title"] for item in output["results"]] == ["Existing onePA event"]
    assert output["partial"] is True
    studio_debug = next(
        row for row in output["debug_by_source"]
        if row.get("adapter") == "studio_published_rule"
    )
    assert studio_debug["source"] == "Esplanade"
    assert studio_debug["complete"] is False
    assert studio_debug["status"] == "failed"
    assert studio_debug["reason_counts"] == {"studio_browser_start_failed": 1}
    assert "fixture browser startup failure" in studio_debug["detail"]
