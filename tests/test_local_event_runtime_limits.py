from __future__ import annotations

from .conftest import read_text


def test_job_detail_budget_matches_total_event_budget() -> None:
    script = read_text("surface/jobs/local_event_search.py")

    assert 'LOCAL_EVENTS_DETAIL_LIMIT", "6"' not in script
    assert 'os.environ["LOCAL_EVENTS_MAX_TOTAL_EVENTS"]' in script
    assert 'LOCAL_EVENTS_DETAIL_TIMEOUT_MS", "60000"' in script


def test_global_collector_never_writes_display_runtime() -> None:
    script = read_text("surface/jobs/local_event_search.py")

    assert 'COLLECTOR_OUT = ENV_DIR / "local_event_search_results.partial.json"' in script
    assert 'write_policy"] = "collector_diagnostics_only"' in script
    assert 'display_runtime_unchanged"] = True' in script
    assert 'OUT.write_text' not in script
    assert 'review_runtime_authority.apply()' not in script
    assert 'listing_only_runtime_authority.apply()' not in script


def test_review_publisher_is_the_only_display_runtime_writer() -> None:
    publisher = read_text(
        "surface/local_events_runtime/review_publish_authority.py"
    )

    assert 'local_event_search_results.json' in publisher
    assert 'write_policy": "review_state_authoritative"' in publisher
    assert 'candidate.decision == "confirmed"' in publisher
    assert "normalize_payload" not in publisher
