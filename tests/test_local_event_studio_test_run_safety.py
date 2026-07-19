from __future__ import annotations

import json
from pathlib import Path

import pytest

from surface.local_events_runtime.studio_evaluate import latest_test_run
from surface.local_events_runtime.studio_rules import RuleStorageError

pytestmark = pytest.mark.backend

SOURCE_ID = "esplanade"
LISTING_URL = "https://www.esplanade.com/whats-on"


def test_latest_test_run_rejects_symlinked_source_directory(tmp_path: Path) -> None:
    test_root = tmp_path / "test-runs"
    test_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (test_root / SOURCE_ID).symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(RuleStorageError, match="source directory must not be a symlink"):
        latest_test_run(SOURCE_ID, LISTING_URL, root=tmp_path)


def test_latest_test_run_skips_symlink_record(tmp_path: Path) -> None:
    directory = tmp_path / "test-runs" / SOURCE_ID
    directory.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "source_id": SOURCE_ID,
                "listing_url": LISTING_URL,
                "run_id": "outside",
                "publishable": True,
            }
        ),
        encoding="utf-8",
    )
    try:
        (directory / "99999999T999999999999Z-outside.json").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert latest_test_run(SOURCE_ID, LISTING_URL, root=tmp_path) is None


def test_latest_test_run_skips_record_with_wrong_source_identity(tmp_path: Path) -> None:
    directory = tmp_path / "test-runs" / SOURCE_ID
    directory.mkdir(parents=True)
    (directory / "20260719T040506000000Z-wrong.json").write_text(
        json.dumps(
            {
                "source_id": "onepa",
                "listing_url": LISTING_URL,
                "run_id": "wrong-source",
                "publishable": True,
            }
        ),
        encoding="utf-8",
    )

    assert latest_test_run(SOURCE_ID, LISTING_URL, root=tmp_path) is None
