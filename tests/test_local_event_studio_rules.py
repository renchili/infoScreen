from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from surface.local_events_runtime import studio_rules
from surface.local_events_runtime.studio_rules import (
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
    title_selector: str = "h2",
) -> dict:
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
        "fields": {
            "title": {"selector": title_selector},
            "when": {"selector": ".event-date"},
            "where": {
                "selector": ".event-venue",
                "allow_source_default": False,
            },
            "url": {
                "selector": "a[href]",
                "attribute": "href",
            },
            "summary": {
                "selector": ".event-description",
                "optional": True,
            },
        },
        "detail_page": {
            "enabled": True,
            "fields": {
                "when": {"selector": ".detail-date"},
                "where": {
                    "selector": ".detail-venue",
                    "allow_source_default": False,
                },
            },
        },
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


def test_rule_schema_rejects_extra_fields_and_invalid_published_contract() -> None:
    extra = draft_payload()
    extra["fields"]["unsupported"] = {"selector": ".bad"}
    with pytest.raises(ValidationError):
        LocalEventStudioRule.model_validate(extra)

    incomplete = draft_payload()
    incomplete["status"] = "published"
    incomplete["version"] = 1
    incomplete["fields"]["where"] = None
    with pytest.raises(ValidationError, match="missing required fields"):
        LocalEventStudioRule.model_validate(incomplete)

    bad_url_field = draft_payload()
    bad_url_field["fields"]["url"]["attribute"] = "src"
    with pytest.raises(ValidationError, match="href"):
        LocalEventStudioRule.model_validate(bad_url_field)


def test_store_rejects_unknown_source_and_unconfigured_listing(
    store: LocalEventStudioRuleStore,
) -> None:
    unknown_source = draft_payload()
    unknown_source["source_id"] = "../../outside"
    with pytest.raises(UnknownSourceError):
        store.save_draft(unknown_source)

    unknown_listing = draft_payload()
    unknown_listing["listing_url"] = "https://www.esplanade.com/not-configured"
    with pytest.raises(UnknownListingError):
        store.save_draft(unknown_listing)


def test_draft_round_trip_is_canonical_and_replaces_atomically(
    store: LocalEventStudioRuleStore,
) -> None:
    first = store.save_draft(draft_payload())
    assert first.listing_url == "https://www.esplanade.com/whats-on"
    assert first.card is not None
    assert first.card.exclude_selectors == [".promotion-card"]

    updated = store.save_draft(draft_payload(title_selector="h3"))
    loaded = store.load_draft("esplanade", "https://www.esplanade.com/whats-on/")
    assert loaded is not None
    assert loaded.fields.title is not None
    assert loaded.fields.title.selector == "h3"
    assert updated.created_at == first.created_at
    assert updated.updated_at is not None
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


def test_publish_creates_monotonic_immutable_history(
    store: LocalEventStudioRuleStore,
) -> None:
    store.save_draft(draft_payload(card_selector="main .event-card-v1"))
    first = store.publish("esplanade", "https://www.esplanade.com/whats-on")
    assert first.status == "published"
    assert first.version == 1
    assert store.load_draft("esplanade", "https://www.esplanade.com/whats-on") is None

    first_export = store.export_rule(
        "esplanade",
        "https://www.esplanade.com/whats-on",
        version=1,
    )

    store.save_draft(draft_payload(card_selector="main .event-card-v2"))
    second = store.publish("esplanade", "https://www.esplanade.com/whats-on/")
    assert second.version == 2
    assert second.card is not None
    assert second.card.selector == "main .event-card-v2"

    history = store.list_history("esplanade", "https://www.esplanade.com/whats-on")
    assert [item.version for item in history] == [1, 2]
    assert history[0].card is not None
    assert history[0].card.selector == "main .event-card-v1"
    assert (
        store.export_rule(
            "esplanade",
            "https://www.esplanade.com/whats-on",
            version=1,
        )
        == first_export
    )


def test_rollback_republishes_history_as_new_version(
    store: LocalEventStudioRuleStore,
) -> None:
    store.save_draft(draft_payload(card_selector=".v1"))
    store.publish("esplanade", "https://www.esplanade.com/whats-on")
    store.save_draft(draft_payload(card_selector=".v2"))
    store.publish("esplanade", "https://www.esplanade.com/whats-on")

    rolled_back = store.rollback(
        "esplanade",
        "https://www.esplanade.com/whats-on",
        1,
    )
    assert rolled_back.version == 3
    assert rolled_back.based_on_version == 1
    assert rolled_back.card is not None
    assert rolled_back.card.selector == ".v1"
    assert [
        item.version
        for item in store.list_history(
            "esplanade",
            "https://www.esplanade.com/whats-on",
        )
    ] == [1, 2, 3]


def test_export_import_validates_and_imports_only_as_draft(
    store: LocalEventStudioRuleStore,
) -> None:
    store.save_draft(draft_payload())
    store.publish("esplanade", "https://www.esplanade.com/whats-on")
    exported = store.export_rule(
        "esplanade",
        "https://www.esplanade.com/whats-on",
    )

    imported = store.import_draft(exported)
    assert imported.status == "draft"
    assert imported.version == 0
    assert imported.published_at is None

    tampered = json.loads(exported)
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
