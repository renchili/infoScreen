from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from surface.local_events_runtime.studio_rules import (
    LocalEventStudioRuleStore,
    RuleStorageError,
    canonical_listing_url,
)

pytestmark = pytest.mark.backend

SOURCE_ID = "esplanade"
LISTING_URL = "https://www.esplanade.com/whats-on"


def source_config(tmp_path: Path) -> Path:
    path = tmp_path / "event_sources.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "id": SOURCE_ID,
                        "name": "Esplanade",
                        "allowed_domains": ["esplanade.com"],
                        "listing_urls": [LISTING_URL],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def draft() -> dict:
    return {
        "schema_version": 1,
        "source_id": SOURCE_ID,
        "listing_url": LISTING_URL,
        "version": 0,
        "status": "draft",
        "card": {"selector": "article.event-card", "exclude_selectors": []},
        "fields": {
            "title": {"selector": "h2"},
            "when": {"selector": "time"},
            "where": {"selector": ".venue", "allow_source_default": False},
            "url": {"selector": "a[href]", "attribute": "href"},
        },
        "detail_page": {"enabled": False, "fields": {}},
        "validation": {
            "require_public_detail_url": True,
            "require_current_or_future_date": True,
        },
    }


def listing_key() -> str:
    canonical = canonical_listing_url(LISTING_URL)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def test_save_rejects_symlink_listing_directory(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    source_dir = root / "rules" / SOURCE_ID
    source_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    binding = source_dir / listing_key()
    try:
        binding.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    store = LocalEventStudioRuleStore(root=root, source_config_path=source_config(tmp_path))
    with pytest.raises(RuleStorageError, match="listing directory must not be a symlink"):
        store.save_draft(draft())
    assert not list(outside.iterdir())


def test_load_rejects_symlink_rule_file(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    config = source_config(tmp_path)
    store = LocalEventStudioRuleStore(root=root, source_config_path=config)
    saved = store.save_draft(draft())
    rule_path = root / "rules" / SOURCE_ID / listing_key() / "draft.json"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(saved.model_dump(mode="json", exclude_none=True)), encoding="utf-8")
    rule_path.unlink()
    try:
        rule_path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(RuleStorageError, match="refusing to read symlink rule"):
        store.load_draft(SOURCE_ID, LISTING_URL)


def test_history_write_rejects_symlink_history_directory(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    config = source_config(tmp_path)
    store = LocalEventStudioRuleStore(root=root, source_config_path=config)
    store.save_draft(draft())
    binding = root / "rules" / SOURCE_ID / listing_key()
    outside = tmp_path / "outside-history"
    outside.mkdir()
    history = binding / "history"
    try:
        history.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(RuleStorageError, match="history directory must not be a symlink"):
        store.publish(SOURCE_ID, LISTING_URL)
    assert not list(outside.iterdir())
