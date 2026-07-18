from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from surface.local_events_runtime import studio_capture
from surface.local_events_runtime.studio_capture import (
    capture_snapshot,
    list_snapshots,
    snapshot_asset_path,
)
from surface.local_events_runtime.studio_rules import UnknownListingError, UnknownSourceError

pytestmark = pytest.mark.backend

PNG = b"\x89PNG\r\n\x1a\nfixture-png"


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
                        "listing_urls": ["https://www.esplanade.com/whats-on"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def fake_capture(source: dict, listing_url: str) -> dict:
    assert source["id"] == "esplanade"
    assert listing_url == "https://www.esplanade.com/whats-on"
    return {
        "final_url": listing_url,
        "page_title": "What's On",
        "prepare": {"clicks": 2, "height": 3200},
        "html": "<html><body><main data-infoscreen-studio-id='e00001'>Events</main></body></html>",
        "screenshot": PNG,
        "dom": {
            "schema_version": 1,
            "page": {
                "url": listing_url,
                "document_width": 1440,
                "document_height": 3200,
            },
            "candidate_count": 1,
            "element_count": 1,
            "truncated": False,
            "elements": [
                {
                    "id": "e00001",
                    "parent_id": None,
                    "tag": "main",
                    "selector": "main",
                    "text": "Events",
                    "href": "",
                    "src": "",
                    "attributes": {},
                    "rect": {"x": 0, "y": 0, "width": 1440, "height": 500},
                }
            ],
        },
    }


def test_capture_snapshot_writes_atomic_complete_bundle(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    captured_at = datetime(2026, 7, 19, 4, 5, 6, 123456, tzinfo=timezone.utc)
    metadata = capture_snapshot(
        "esplanade",
        "https://www.esplanade.com/whats-on/",
        root=root,
        source_config_path=write_source_config(tmp_path),
        capture_page=fake_capture,
        now_fn=lambda: captured_at,
    )

    assert metadata["snapshot_id"] == "20260719T040506123456Z-2d47d69be6"
    assert metadata["source_id"] == "esplanade"
    assert metadata["listing_url"] == "https://www.esplanade.com/whats-on"
    assert metadata["dom_element_count"] == 1

    directory = root / "snapshots" / "esplanade" / metadata["snapshot_id"]
    assert (directory / "page.png").read_bytes() == PNG
    assert "data-infoscreen-studio-id" in (directory / "page.html").read_text(encoding="utf-8")
    assert json.loads((directory / "dom.json").read_text(encoding="utf-8"))["element_count"] == 1
    assert json.loads((directory / "metadata.json").read_text(encoding="utf-8"))["snapshot_id"] == metadata["snapshot_id"]
    assert not list(root.rglob("*.tmp"))


def test_snapshot_catalog_and_asset_resolution_are_confined(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    metadata = capture_snapshot(
        "esplanade",
        "https://www.esplanade.com/whats-on",
        root=root,
        source_config_path=write_source_config(tmp_path),
        capture_page=fake_capture,
        now_fn=lambda: datetime(2026, 7, 19, tzinfo=timezone.utc),
    )

    catalog = list_snapshots(
        root=root,
        source_id="esplanade",
        listing_url="https://www.esplanade.com/whats-on/",
    )
    assert [item["snapshot_id"] for item in catalog] == [metadata["snapshot_id"]]

    screenshot = snapshot_asset_path(
        "esplanade",
        metadata["snapshot_id"],
        "page.png",
        root=root,
    )
    assert screenshot is not None
    assert screenshot.read_bytes() == PNG
    assert snapshot_asset_path("../outside", metadata["snapshot_id"], "page.png", root=root) is None
    assert snapshot_asset_path("esplanade", "../../outside", "page.png", root=root) is None
    assert snapshot_asset_path("esplanade", metadata["snapshot_id"], "../../secret", root=root) is None


def test_capture_rejects_unknown_source_and_listing_before_browser_call(tmp_path: Path) -> None:
    config = write_source_config(tmp_path)
    called = False

    def should_not_run(source: dict, listing_url: str) -> dict:
        nonlocal called
        called = True
        return fake_capture(source, listing_url)

    with pytest.raises(UnknownSourceError):
        capture_snapshot(
            "../../outside",
            "https://www.esplanade.com/whats-on",
            root=tmp_path / "studio",
            source_config_path=config,
            capture_page=should_not_run,
        )
    with pytest.raises(UnknownListingError):
        capture_snapshot(
            "esplanade",
            "https://www.esplanade.com/not-configured",
            root=tmp_path / "studio",
            source_config_path=config,
            capture_page=should_not_run,
        )
    assert called is False


def test_failed_directory_publish_leaves_no_partial_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "studio"

    def fail_replace(source: object, target: object) -> None:
        raise OSError("simulated snapshot publish failure")

    monkeypatch.setattr(studio_capture.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated snapshot publish failure"):
        capture_snapshot(
            "esplanade",
            "https://www.esplanade.com/whats-on",
            root=root,
            source_config_path=write_source_config(tmp_path),
            capture_page=fake_capture,
            now_fn=lambda: datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    assert not list((root / "snapshots").rglob("metadata.json"))
    assert not list((root / "snapshots").rglob("*.tmp"))


def test_dom_capture_script_marks_elements_without_network_payload_collection() -> None:
    script = studio_capture.DOM_EVIDENCE_JS
    assert "data-infoscreen-studio-id" in script
    assert "getBoundingClientRect" in script
    assert "XMLHttpRequest" not in script
    assert "performance.getEntries" not in script
    assert "response.body" not in script
