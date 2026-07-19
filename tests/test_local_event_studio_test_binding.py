from __future__ import annotations

import json
from pathlib import Path

import pytest

from surface.local_events_runtime.studio_evaluate import latest_test_run
from .conftest import read_text

pytestmark = pytest.mark.backend

SOURCE_ID = "esplanade"
LISTING_A = "https://www.esplanade.com/whats-on"
LISTING_B = "https://www.esplanade.com/whats-on/festivals-and-series"


def write_run(directory: Path, filename: str, listing_url: str, run_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_id": SOURCE_ID,
                "listing_url": listing_url,
                "run_id": run_id,
                "snapshot_id": "20260719T040506123456Z-4183667b5e",
                "tested_at": "2026-07-19T04:05:06.123456+00:00",
                "rule_fingerprint": "a" * 64,
                "matched_card_count": 1,
                "accepted_count": 1,
                "rejected_count": 0,
                "publishable": True,
                "accepted": [],
                "rejected": [],
            }
        ),
        encoding="utf-8",
    )


def test_latest_test_run_skips_newer_run_for_another_listing(tmp_path: Path) -> None:
    directory = tmp_path / "test-runs" / SOURCE_ID
    write_run(directory, "20260719T040506000000Z-a.json", LISTING_A, "listing-a-run")
    write_run(directory, "20260719T050506000000Z-b.json", LISTING_B, "newer-listing-b-run")

    selected = latest_test_run(SOURCE_ID, LISTING_A, root=tmp_path)

    assert selected is not None
    assert selected["run_id"] == "listing-a-run"
    assert selected["listing_url"] == LISTING_A


def test_latest_test_run_without_listing_preserves_legacy_source_latest_behavior(tmp_path: Path) -> None:
    directory = tmp_path / "test-runs" / SOURCE_ID
    write_run(directory, "20260719T040506000000Z-a.json", LISTING_A, "older-run")
    write_run(directory, "20260719T050506000000Z-b.json", LISTING_B, "newer-run")

    selected = latest_test_run(SOURCE_ID, root=tmp_path)

    assert selected is not None
    assert selected["run_id"] == "newer-run"


def test_http_latest_test_route_passes_canonical_listing_to_lookup() -> None:
    source = read_text("surface/serve_infoscreen.py")
    assert "latest_test_run(source_id, canonical_url, root=studio_root())" in source
    assert "latest_test_run(source_id, root=studio_root())" not in source
