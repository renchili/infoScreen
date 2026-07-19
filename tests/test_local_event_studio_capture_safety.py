from __future__ import annotations

from pathlib import Path

import pytest

from surface.local_events_runtime.studio_capture import (
    DOM_EVIDENCE_JS,
    snapshot_asset_path,
    write_snapshot,
)
from surface.local_events_runtime.studio_rules import RuleStorageError

pytestmark = pytest.mark.backend

SOURCE_ID = "esplanade"
SNAPSHOT_ID = "20260719T040506123456Z-4183667b5e"
PNG = b"\x89PNG\r\n\x1a\nfixture"


def metadata() -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "source_id": SOURCE_ID,
        "source_name": "Esplanade",
        "listing_url": "https://www.esplanade.com/whats-on",
        "final_url": "https://www.esplanade.com/whats-on",
        "page_title": "What's On",
        "captured_at": "2026-07-19T04:05:06.123456+00:00",
        "prepare": {},
        "dom_element_count": 1,
        "dom_truncated": False,
        "assets": {"screenshot": "page.png", "html": "page.html", "dom": "dom.json"},
    }


def dom() -> dict:
    return {
        "schema_version": 1,
        "page": {"document_width": 1440, "document_height": 1000},
        "candidate_count": 1,
        "element_count": 1,
        "truncated": False,
        "elements": [],
    }


def test_capture_script_saves_every_attribute_used_by_generated_or_image_rules() -> None:
    for name in [
        "data-testid",
        "data-test",
        "data-component",
        "data-module",
        "data-src",
        "data-lazy-src",
    ]:
        assert f'"{name}"' in DOM_EVIDENCE_JS
    assert "stableName(el.id)" in DOM_EVIDENCE_JS
    assert "stableAttributeValue(value)" in DOM_EVIDENCE_JS
    assert "el.hasAttribute(\"data-src\")" in DOM_EVIDENCE_JS
    assert "el.hasAttribute(\"data-lazy-src\")" in DOM_EVIDENCE_JS


def test_capture_script_includes_ancestors_and_records_only_direct_parent_ids() -> None:
    assert "const selectedSet = new Set()" in DOM_EVIDENCE_JS
    assert "lineage.unshift(current)" in DOM_EVIDENCE_JS
    assert 'el.parentElement.hasAttribute("data-infoscreen-studio-id")' in DOM_EVIDENCE_JS
    assert 'el.parentElement.closest("[data-infoscreen-studio-id]")' not in DOM_EVIDENCE_JS


def test_snapshot_write_rejects_symlink_source_directory(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    snapshots = root / "snapshots"
    snapshots.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    source_link = snapshots / SOURCE_ID
    try:
        source_link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(RuleStorageError, match="source directory must not be a symlink"):
        write_snapshot(root, metadata(), screenshot=PNG, html="<html></html>", dom=dom())
    assert not list(outside.iterdir())


def test_snapshot_asset_rejects_symlinked_source_or_asset(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    target = root / "snapshots" / SOURCE_ID / SNAPSHOT_ID
    target.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    asset = target / "page.png"
    try:
        asset.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert snapshot_asset_path(SOURCE_ID, SNAPSHOT_ID, "page.png", root=root) is None


def test_snapshot_asset_rejects_symlinked_snapshot_root(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    root.mkdir()
    outside = tmp_path / "outside-snapshots"
    asset = outside / SOURCE_ID / SNAPSHOT_ID / "page.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(PNG)
    try:
        (root / "snapshots").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert snapshot_asset_path(SOURCE_ID, SNAPSHOT_ID, "page.png", root=root) is None
