from __future__ import annotations

import json
import sys
from pathlib import Path

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime.event_review import (  # noqa: E402
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
)
from local_events_runtime.review_collection_jobs import CollectionStoreView  # noqa: E402


def test_scoped_collection_view_does_not_mutate_listing_decisions(tmp_path: Path) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "museum",
                        "name": "Museum",
                        "allowed_domains": ["museum.example"],
                        "listing_urls": ["https://museum.example/events"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = EventReviewStore(root=tmp_path / "review", config_path=config)
    first = ListingPageCandidate(
        candidate_id="first",
        source_id="museum",
        source_name="Museum",
        url="https://museum.example/events",
        origin="configured",
        decision="pending",
        discovered_at="2099-01-01T00:00:00+00:00",
    )
    second = ListingPageCandidate(
        candidate_id="second",
        source_id="museum",
        source_name="Museum",
        url="https://museum.example/programmes",
        origin="discovered",
        decision="confirmed",
        discovered_at="2099-01-01T00:00:00+00:00",
    )
    store.save(ReviewState(listing_pages=[first, second]))

    import threading

    scoped = CollectionStoreView(store, threading.RLock(), ["first"])
    visible = scoped.load()

    assert [row.candidate_id for row in visible.listing_pages if row.decision == "confirmed"] == ["first"]
    persisted = store.load()
    assert next(row for row in persisted.listing_pages if row.candidate_id == "first").decision == "pending"
    assert next(row for row in persisted.listing_pages if row.candidate_id == "second").decision == "confirmed"


def test_review_collector_is_wrapped_after_diagnostics() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    diagnostics = bootstrap.index("apply_event_review_diagnostics()")
    publisher = bootstrap.index("apply_review_publish_authority()")
    background = bootstrap.index("apply_async_collection()")

    assert diagnostics < publisher < background
    assert "existing synchronous POST handler into a background-job starter" in bootstrap


def test_collect_events_is_not_a_blocking_overlay_request() -> None:
    blocker = read_text("surface/web/assets/js/local_event_review_blocking.js")

    assert '"/api/local-events/review/collect-events"' not in blocker
    assert '"/api/local-events/review/discover-listings"' in blocker


def test_review_job_client_polls_state_and_survives_page_reload() -> None:
    client = read_text("surface/web/assets/js/local_event_review_jobs.js")
    studio = read_text("surface/web/local-events/studio/index.html")

    assert 'const COLLECTION_PATH = "/api/local-events/review/collect-events"' in client
    assert 'const STATE_PATH = "/api/local-events/review/state"' in client
    assert "sharedPoll(job.job_id)" in client
    assert 'document.addEventListener("DOMContentLoaded", resumeRunningJob)' in client
    assert 'src="/assets/js/local_event_review_jobs.js"' in studio
    assert studio.index("local_event_review_blocking.js") < studio.index("local_event_review_jobs.js")
    assert studio.index("local_event_review_jobs.js") < studio.index("local_event_studio.js")


def test_background_authority_returns_immediately_with_job_state() -> None:
    authority = read_text(
        "surface/local_events_runtime/review_async_collection_authority.py"
    )
    manager = read_text(
        "surface/local_events_runtime/review_collection_jobs.py"
    )

    assert "JOBS.start(" in authority
    assert '"background_job": job' in authority
    assert 'payload["event_collection_job"] = JOBS.snapshot()' in authority
    assert "threading.Thread(" in manager
    assert "daemon=True" in manager
    assert "return self.snapshot_unlocked()" in manager
