from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from surface.local_events_runtime import studio_rules
from surface.local_events_runtime.studio_rules import (
    BrowserActionRule,
    LocalEventStudioRule,
    LocalEventStudioRuleStore,
    RuleNotFoundError,
    UnknownListingError,
    UnknownSourceError,
)

pytestmark = pytest.mark.backend


def write_source_config(tmp_path: Path) -> Path:
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
                        "listing_urls": [
                            "https://www.esplanade.com/whats-on",
                            "https://www.esplanade.com/whats-on?genre=music",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def draft_payload(
    *,
    card_selector: str = "main .event-card",
    title_selector: str | None = "h2",
) -> dict:
    listing_fields: dict = {
        "when": {"selector": ".event-date"},
        "where": {
            "selector": ".event-venue",
            "allow_source_default": False,
        },
        "url": {"selector": "a[href]", "attribute": "href"},
        "summary": {"selector": ".event-description", "optional": True},
    }
    if title_selector is not None:
        listing_fields["title"] = {"selector": title_selector}
    return {
        "schema_version": 1,
        "source_id": "esplanade",
        "listing_url": "https://www.esplanade.com/whats-on/",
        "status": "draft",
        "version": 0,
        "card": {
            "selector": card_selector,
            "exclude_selectors": [".promotion-card", ".promotion-card"],
        },
        "fields": listing_fields,
        "detail_page": {
            "enabled": True,
            "fields": {
                "title": {"selector": "h1"},
                "when": {"selector": ".detail-date"},
                "where": {
                    "selector": ".detail-venue",
                    "allow_source_default": False,
                },
            },
        },
        "listing_actions": [
            {
                "action": "click",
                "selector": "button.accept-cookie",
                "optional": True,
                "wait_ms": 300,
            },
            {
                "action": "click_repeat",
                "selector": "button.load-more",
                "optional": True,
                "max_rounds": 10,
                "wait_ms": 500,
            },
        ],
        "detail_actions": [
            {
                "action": "click",
                "selector": "button.expand-details",
                "optional": True,
                "wait_ms": 200,
            }
        ],
        "validation": {
            "require_public_detail_url": True,
            "require_current_or_future_date": True,
        },
    }


@pytest.fixture()
def store(tmp_path: Path) -> LocalEventStudioRuleStore:
    return LocalEventStudioRuleStore(
        root=tmp_path / "studio",
        source_config_path=write_source_config(tmp_path),
    )


def test_rule_schema_rejects_extra_fields_and_invalid_attributes() -> None:
    extra = draft_payload()
    extra["fields"]["unsupported"] = {"selector": ".bad"}
    with pytest.raises(ValidationError):
        LocalEventStudioRule.model_validate(extra)

    bad_url = draft_payload()
    bad_url["fields"]["url"]["attribute"] = "src"
    with pytest.raises(ValidationError, match="href"):
        LocalEventStudioRule.model_validate(bad_url)


def test_published_required_fields_may_come_from_listing_or_detail() -> None:
    detail_title = draft_payload(title_selector=None)
    detail_title["status"] = "published"
    detail_title["version"] = 1
    parsed = LocalEventStudioRule.model_validate(detail_title)
    assert parsed.fields.title is None
    assert parsed.detail_page.fields.title is not None

    missing_where = draft_payload()
    missing_where["status"] = "published"
    missing_where["version"] = 1
    missing_where["fields"].pop("where")
    missing_where["detail_page"]["fields"].pop("where")
    with pytest.raises(ValidationError, match="required listing/detail fields"):
        LocalEventStudioRule.model_validate(missing_where)

    missing_url = draft_payload()
    missing_url["status"] = "published"
    missing_url["version"] = 1
    missing_url["fields"].pop("url")
    with pytest.raises(ValidationError, match="url"):
        LocalEventStudioRule.model_validate(missing_url)


def test_browser_actions_have_typed_replay_contracts() -> None:
    click = BrowserActionRule.model_validate(
        {
            "action": "click",
            "selector": "button.accept-cookie",
            "optional": True,
            "wait_ms": 400,
        }
    )
    assert click.selector == "button.accept-cookie"
    assert click.optional is True

    with pytest.raises(ValidationError, match="requires a selector"):
        BrowserActionRule.model_validate({"action": "click"})
    with pytest.raises(ValidationError, match="requires a value"):
        BrowserActionRule.model_validate(
            {"action": "select_option", "selector": "select.genre"}
        )
    with pytest.raises(ValidationError, match="only valid for click_repeat"):
        BrowserActionRule.model_validate(
            {"action": "click", "selector": "button", "max_rounds": 2}
        )


def test_store_rejects_unknown_binding(store: LocalEventStudioRuleStore) -> None:
    unknown_source = draft_payload()
    unknown_source["source_id"] = "../../outside"
    with pytest.raises(UnknownSourceError):
        store.save_draft(unknown_source)

    unknown_listing = draft_payload()
    unknown_listing["listing_url"] = "https://www.esplanade.com/not-configured"
    with pytest.raises(UnknownListingError):
        store.save_draft(unknown_listing)


def test_draft_round_trip_is_canonical_and_atomic(
    store: LocalEventStudioRuleStore,
) -> None:
    first = store.save_draft(draft_payload())
    assert first.listing_url == "https://www.esplanade.com/whats-on"
    assert first.card is not None
    assert first.card.exclude_selectors == [".promotion-card"]
    assert [item.action for item in first.listing_actions] == [
        "click",
        "click_repeat",
    ]

    updated_payload = draft_payload(title_selector="h3")
    updated = store.save_draft(updated_payload)
    loaded = store.load_draft("esplanade", "https://www.esplanade.com/whats-on/")
    assert loaded is not None
    assert loaded.fields.title is not None
    assert loaded.fields.title.selector == "h3"
    assert updated.created_at == first.created_at
    assert not list(store.root.rglob("*.tmp"))


def test_failed_atomic_replace_preserves_previous_draft(
    store: LocalEventStudioRuleStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.save_draft(draft_payload(title_selector="h2"))

    def fail_replace(source: object, target: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(studio_rules.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store.save_draft(draft_payload(title_selector="h3"))

    loaded = store.load_draft("esplanade", "https://www.esplanade.com/whats-on")
    assert loaded is not None
    assert loaded.fields.title is not None
    assert loaded.fields.title.selector == "h2"
    assert not list(store.root.rglob("*.tmp"))


def test_publish_history_rollback_and_import(store: LocalEventStudioRuleStore) -> None:
    store.save_draft(draft_payload(card_selector="main .event-card-v1"))
    first = store.publish("esplanade", "https://www.esplanade.com/whats-on")
    assert first.version == 1
    assert first.status == "published"
    assert store.load_draft("esplanade", "https://www.esplanade.com/whats-on") is None

    first_export = store.export_rule(
        "esplanade",
        "https://www.esplanade.com/whats-on",
        version=1,
    )
    store.save_draft(draft_payload(card_selector="main .event-card-v2"))
    second = store.publish("esplanade", "https://www.esplanade.com/whats-on")
    assert second.version == 2

    history = store.list_history("esplanade", "https://www.esplanade.com/whats-on")
    assert [item.version for item in history] == [1, 2]
    assert history[0].listing_actions[1].action == "click_repeat"
    assert store.export_rule(
        "esplanade",
        "https://www.esplanade.com/whats-on",
        version=1,
    ) == first_export

    rolled_back = store.rollback(
        "esplanade",
        "https://www.esplanade.com/whats-on",
        1,
    )
    assert rolled_back.version == 3
    assert rolled_back.based_on_version == 1
    assert rolled_back.card is not None
    assert rolled_back.card.selector == "main .event-card-v1"

    imported = store.import_draft(first_export)
    assert imported.status == "draft"
    assert imported.version == 0
    assert imported.published_at is None
    assert imported.detail_actions[0].selector == "button.expand-details"

    tampered = json.loads(first_export)
    tampered["listing_url"] = "https://evil.example/events"
    with pytest.raises(UnknownListingError):
        store.import_draft(tampered)


def test_missing_draft_and_history_are_specific_errors(
    store: LocalEventStudioRuleStore,
) -> None:
    with pytest.raises(RuleNotFoundError):
        store.publish("esplanade", "https://www.esplanade.com/whats-on")
    with pytest.raises(RuleNotFoundError):
        store.rollback("esplanade", "https://www.esplanade.com/whats-on", 99)
