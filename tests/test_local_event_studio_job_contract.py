from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.backend

ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "surface" / "jobs" / "local_event_search.py"


def test_local_event_job_applies_studio_between_collection_and_normalization() -> None:
    source = JOB_PATH.read_text(encoding="utf-8")

    collect_stage = source.index("legacy_payload = collect_events(CONFIG, location, DEBUG_DIR)")
    studio_stage = source.index("routed_payload = apply_runtime_studio_rules(legacy_payload)")
    normalize_stage = source.index("normalize_payload(routed_payload)")

    assert collect_stage < studio_stage < normalize_stage
    assert "from local_events_runtime.studio_pipeline import apply_runtime_studio_rules" in source


def test_local_event_job_keeps_existing_writer_and_partial_protection() -> None:
    source = JOB_PATH.read_text(encoding="utf-8")
    assert "verified_previous_payload" in source
    assert "kept_previous_verified_result" in source
    assert "write_payload" in source
    assert "apply_detail_authority" not in source
    assert "apply_listing_url_authority" not in source
    assert "apply_source_overrides" not in source


def test_local_event_job_uses_active_runtime_directory() -> None:
    source = JOB_PATH.read_text(encoding="utf-8")
    assert 'os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))' in source
    assert "ENV_DIR.mkdir(parents=True, exist_ok=True)" in source
