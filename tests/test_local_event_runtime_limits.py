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
    assert "MIN_DETAIL_TIMEOUT_MS = 60000" in authority
    assert "max_cards=max(int(max_cards), int(_extract.MAX_EVENTS_PER_SOURCE))" in authority


def test_supported_bootstrap_applies_coverage_before_review_modules() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    coverage = bootstrap.index("apply_complete_collection()")
    detail = bootstrap.index("apply_detail_date_authority()")
    review = bootstrap.index("apply_review_publish_authority()")

    assert coverage < detail < review


def test_job_writes_primary_and_partial_outputs_with_review_overlay() -> None:
    script = read_text("surface/jobs/local_event_search.py")

    assert 'OUT = ENV_DIR / "local_event_search_results.json"' in script
    assert 'PARTIAL_OUT = ENV_DIR / "local_event_search_results.partial.json"' in script
    assert "merge_review_state" in script
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


def test_review_publisher_overlays_without_normalizing_collector_rows() -> None:
    publisher = read_text(
        "surface/local_events_runtime/review_publish_authority.py"
    )

    assert "overlay_on_collector_results" in publisher
    assert "system_results" in publisher
    assert 'item.get("review_publish_origin") != _REVIEW_PUBLISH_ORIGIN' in publisher
    assert "normalize_payload" not in publisher
    assert "candidate.decision == \"confirmed\"" in publisher
