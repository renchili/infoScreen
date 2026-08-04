from __future__ import annotations

from datetime import date

from surface.local_events_runtime import review_expiry_authority as expiry
from surface.local_events_runtime import review_publish_authority as publisher
from surface.local_events_runtime.event_review import (
    EventCandidate,
    EventEvidence,
    EventReviewStore,
    ReviewState,
)

from .conftest import read_text


def _candidate(title: str, when: str) -> EventCandidate:
    slug = title.casefold().replace(" ", "-")
    return EventCandidate(
        candidate_id=f"candidate-{slug}",
        source_id="artscience",
        source_name="ArtScience Museum",
        listing_url="https://example.com/events",
        detail_url=f"https://example.com/events/{slug}",
        title=title,
        when=when,
        where="ArtScience Museum",
        summary="Official exhibition details.",
        detail_status="collected",
        evidence=EventEvidence(
            selector="article.event",
            selector_index=0,
            selector_match_count=1,
            document_position={"x": 0, "y": 0, "width": 100, "height": 100},
            viewport_position={"x": 0, "y": 0, "width": 100, "height": 100},
            page_index=0,
            page_url="https://example.com/events",
            text=title,
        ),
        decision="confirmed",
        collected_at="2026-01-01T00:00:00+00:00",
    )


def _store(tmp_path) -> EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(
        '{"sources":[{"id":"artscience","name":"ArtScience Museum"}]}',
        encoding="utf-8",
    )
    return EventReviewStore(root=tmp_path / "review", config_path=config)


def test_cross_month_range_is_expired_after_its_end_date() -> None:
    past_year = date.today().year - 1
    future_year = date.today().year + 1

    assert expiry.event_is_expired(
        {"when": f"17 Jan – 10 May {past_year}"}
    )
    assert not expiry.event_is_expired(
        {"when": f"17 Jan – 10 May {future_year}"}
    )
    assert not expiry.event_is_expired(
        {"when": f"From 17 Jan {past_year}"}
    )


def test_studio_payload_hides_expired_candidates_without_deleting_history(tmp_path) -> None:
    past_year = date.today().year - 1
    future_year = date.today().year + 1
    store = _store(tmp_path)
    store.save(
        ReviewState(
            events=[
                _candidate("Expired exhibition", f"17 Jan – 10 May {past_year}"),
                _candidate("Current exhibition", f"17 Jan – 10 May {future_year}"),
            ]
        )
    )

    expiry.apply()
    payload = store.state_payload()

    assert [row["title"] for row in payload["events"]] == ["Current exhibition"]
    assert payload["expired_event_count"] == 1
    assert len(store.load().events) == 2


def test_old_collector_snapshot_cannot_restore_expired_events() -> None:
    past_year = date.today().year - 1
    future_year = date.today().year + 1
    expiry.apply()

    cleaned = publisher.clean_collector_payload(
        {
            "ok": True,
            "count": 2,
            "results": [
                {
                    "title": "Expired exhibition",
                    "when": f"17 Jan – 10 May {past_year}",
                    "url": "https://example.com/events/expired",
                },
                {
                    "title": "Current exhibition",
                    "when": f"17 Jan – 10 May {future_year}",
                    "url": "https://example.com/events/current",
                },
            ],
        }
    )

    assert [row["title"] for row in cleaned["results"]] == ["Current exhibition"]
    assert cleaned["count"] == 1
    assert cleaned["expired_events_removed"] == 1


def test_review_bootstrap_installs_expiry_authority() -> None:
    source = read_text("surface/local_events_runtime/review_summary_authority.py")

    assert "apply_review_expiry_authority" in source
    assert "apply_review_expiry_authority()" in source
