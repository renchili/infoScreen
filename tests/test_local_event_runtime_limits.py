from __future__ import annotations

from .conftest import read_text


def test_complete_collection_authority_lifts_all_coverage_limits() -> None:
    authority = read_text(
        "surface/local_events_runtime/complete_collection_authority.py"
    )

    assert "MIN_TOTAL_SECONDS = 7200.0" in authority
    assert "MIN_SOURCE_SECONDS = 1200.0" in authority
    assert "MIN_SOURCE_CONCURRENCY = 4" in authority
    assert "MIN_EVENTS_PER_SOURCE = 180" in authority
    assert "MIN_TOTAL_EVENTS = 180" in authority
    assert "MIN_LISTING_PAGES = 20" in authority
    assert "MIN_NAV_TIMEOUT_MS = 180000" in authority
    assert "MIN_DOM_TIMEOUT_MS = 180000" in authority
    assert "MIN_LOAD_WAIT_MS = 5000" in authority
    assert "MIN_DETAIL_TIMEOUT_MS = 180000" in authority
    assert "MIN_NAV_TIMEOUT_MS = 25000" not in authority
    assert "MIN_DOM_TIMEOUT_MS = 25000" not in authority
    assert "max_cards=max(int(max_cards), int(_extract.MAX_EVENTS_PER_SOURCE))" in authority


def test_supported_bootstrap_applies_coverage_before_review_modules() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    coverage = bootstrap.index("apply_complete_collection()")
    detail = bootstrap.index("apply_detail_date_authority()")
    summary = bootstrap.index("apply_review_summary_authority()")
    review = bootstrap.index("apply_review_publish_authority()")

    assert coverage < detail < summary < review


def test_job_writes_collector_primary_and_partial_outputs() -> None:
    script = read_text("surface/jobs/local_event_search.py")

    assert 'OUT = ENV_DIR / "local_event_search_results.json"' in script
    assert "COLLECTOR_OUT = ENV_DIR / COLLECTOR_RUNTIME_FILENAME" in script
    assert 'PARTIAL_OUT = ENV_DIR / "local_event_search_results.partial.json"' in script
    assert "load_collector_snapshot" in script
    assert "write_collector_snapshot" in script
    assert "merge_review_state" in script
    assert "review_summary_authority.apply()" in script
    assert "collector_complete_with_review" in script
    assert "kept_previous_verified_result_with_review" in script
    assert "review_runtime_authority.apply()" not in script
    assert "listing_only_runtime_authority.apply()" not in script


def test_deployed_services_allow_complete_collection_duration() -> None:
    local_events = read_text(
        "deploy/systemd/user/infoscreen-local-events.service"
    )
    http = read_text("deploy/systemd/user/infoscreen-http.service")

    assert "TimeoutStartSec=7500" in local_events
    assert "Environment=LOCAL_EVENT_SEARCH_TIMEOUT_SECONDS=7500" in http


def test_review_publisher_projects_without_normalizing_collector_rows() -> None:
    publisher = read_text(
        "surface/local_events_runtime/review_publish_authority.py"
    )

    assert "review_projection_over_collector_snapshot" in publisher
    assert "clean_collector_payload" in publisher
    assert "write_collector_snapshot" in publisher
    assert "suppresses a matching collector row" in publisher
    assert "normalize_payload" not in publisher
    assert 'candidate.decision in accepted' in publisher
    assert 'merged[_REVIEW_OVERLAY_BASE]' not in publisher
