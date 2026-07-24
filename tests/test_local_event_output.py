from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from jobs import local_event_search as job  # noqa: E402
from local_events_runtime.event_review import EventReviewStore, ReviewState  # noqa: E402
from local_events_runtime.output import normalize_payload, plain_text  # noqa: E402

VERIFIED_POLICY = "official-listing-authority-v1"


def future_label(days: int = 30) -> str:
    value = date.today() + timedelta(days=days)
    return f"{value.day} {value.strftime('%b')} {value.year}"


def complete_source(name: str) -> dict:
    return {
        "source": name,
        "listing_urls": [f"https://example.test/{name.lower()}"],
        "listing_fetched": 1,
        "cards_found": 0,
        "accepted": 0,
        "reason_counts": {},
        "not_output_preview": [],
    }


def failed_source(name: str, reason: str = "render_error:TimeoutError") -> dict:
    return {
        "source": name,
        "listing_urls": [f"https://example.test/{name.lower()}"],
        "listing_fetched": 0,
        "cards_found": 0,
        "accepted": 0,
        "reason_counts": {reason: 1},
        "not_output_preview": [{"reason": reason}],
    }


def review_store_at(tmp_path) -> EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "local_event_review", config)
    store.save(ReviewState())
    return store


def test_plain_text_removes_html_markup_and_hidden_content() -> None:
    raw = (
        '<p><strong>About the Event</strong><span style="background-color:#00ffff;"></span></p>'
        '<p>This talk is a compassionate and practical guide.</p>'
        '<ul><li>What to do first</li><li>Where to get help</li></ul>'
        '<script>alert("ignore")</script>'
    )

    assert plain_text(raw) == (
        "About the Event This talk is a compassionate and practical guide. "
        "• What to do first • Where to get help"
    )


def test_plain_text_removes_repeatedly_escaped_detail_markup() -> None:
    raw = (
        "&amp;lt;p&amp;gt;&amp;lt;strong&amp;gt;About the Event&amp;lt;/strong&amp;gt;"
        "&amp;lt;span style=&amp;quot;background-color: transparent;&amp;quot;&amp;gt;"
        "&amp;lt;/span&amp;gt;&amp;lt;/p&amp;gt;"
        "&amp;lt;p&amp;gt;This talk is a compassionate and practical guide to navigating loss."
        "&amp;lt;/p&amp;gt;"
    )

    assert plain_text(raw) == (
        "About the Event This talk is a compassionate and practical guide to navigating loss."
    )


def test_local_event_payload_is_normalized_before_runtime_delivery() -> None:
    payload = {
        "results": [
            {
                "title": "What Happens After Someone Dies: A Practical Guide for Families",
                "when": future_label(),
                "where": "<span>Central Public Library</span>",
                "summary": (
                    '<p><strong>About the Event</strong></p>'
                    '<p>This talk is a compassionate and practical guide to navigating loss.</p>'
                ),
                "url": "https://example.test/events/practical-guide",
                "candidate_policy": VERIFIED_POLICY,
            }
        ]
    }

    normalized = normalize_payload(payload)
    event = normalized["results"][0]

    assert event["where"] == "Central Public Library"
    assert event["summary"] == (
        "This talk is a compassionate and practical guide to navigating loss."
    )
    assert "<" not in event["summary"]
    assert normalized["text_normalizer"] == "plain-text-v1"


def test_description_alias_is_cleaned_and_promoted_to_summary() -> None:
    payload = {
        "results": [
            {
                "title": "What Happens After Someone Dies: A Practical Guide for Families",
                "when": future_label(),
                "where": "Central Public Library",
                "description": (
                    '<p><strong>About the Event</strong></p>'
                    '<p>This talk is a compassionate and practical guide to navigating loss.</p>'
                ),
                "url": "https://example.test/events/practical-guide",
                "candidate_policy": VERIFIED_POLICY,
            }
        ]
    }

    event = normalize_payload(payload)["results"][0]
    expected = "This talk is a compassionate and practical guide to navigating loss."

    assert event["description"] == expected
    assert event["summary"] == expected


def test_local_event_payload_promotes_venue_alias_to_where() -> None:
    normalized = normalize_payload(
        {
            "results": [
                {
                    "title": "Example Event",
                    "when": future_label(),
                    "where": "",
                    "venue": "NLB Building, Level 1",
                    "summary": "Details",
                    "url": "https://example.test/events/example-event",
                    "candidate_policy": VERIFIED_POLICY,
                }
            ]
        }
    )

    assert normalized["results"][0]["where"] == "NLB Building, Level 1"


def test_partial_state_uses_source_completion_not_debug_row_count() -> None:
    payload = job.annotate_source_completion(
        {
            "source_count": 2,
            "debug_by_source": [
                complete_source("NLB"),
                failed_source("SAFRA"),
            ],
            "results": [],
        }
    )

    assert len(payload["debug_by_source"]) == payload["source_count"] == 2
    assert payload["partial"] is True
    assert payload["completed_source_count"] == 1
    assert payload["incomplete_source_count"] == 1
    assert payload["debug_by_source"][0]["status"] == "complete"
    assert payload["debug_by_source"][1]["status"] == "timed_out"


def test_successful_empty_source_is_complete() -> None:
    payload = job.annotate_source_completion(
        {
            "source_count": 1,
            "debug_by_source": [complete_source("EmptyButHealthy")],
            "results": [],
        }
    )

    assert payload["partial"] is False
    assert payload["completed_source_count"] == 1


def test_smaller_partial_refresh_preserves_verified_primary_exactly(
    tmp_path,
    monkeypatch,
) -> None:
    out = tmp_path / "local_event_search_results.json"
    partial_out = tmp_path / "local_event_search_results.partial.json"
    previous_event = {
        "title": "Existing verified Event",
        "when": "Ongoing",
        "where": "Existing Gallery",
        "url": "https://example.test/events/existing",
        "summary": "Preserve this exact persisted row.",
        "candidate_policy": VERIFIED_POLICY,
    }
    out.write_text(
        json.dumps({"results": [previous_event]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "OUT", out)
    monkeypatch.setattr(job, "PARTIAL_OUT", partial_out)

    display = job.write_payload(
        {
            "source_count": 2,
            "debug_by_source": [
                complete_source("NLB"),
                failed_source("SAFRA"),
            ],
            "results": [],
        },
        review_store_at(tmp_path),
    )

    retained = json.loads(out.read_text(encoding="utf-8"))
    partial = json.loads(partial_out.read_text(encoding="utf-8"))

    assert retained["results"] == [previous_event]
    assert display["write_policy"] == "kept_previous_verified_result_with_review"
    assert partial["write_policy"] == "kept_previous_verified_result"
    assert partial["previous_system_count"] == 1


def test_unverified_legacy_rows_are_not_preserved_during_partial_refresh(
    tmp_path,
    monkeypatch,
) -> None:
    out = tmp_path / "local_event_search_results.json"
    partial_out = tmp_path / "local_event_search_results.partial.json"
    out.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "title": "Carpark",
                        "when": future_label(),
                        "where": "SAFRA Clubs",
                        "url": "https://example.test/amenities/carpark",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "OUT", out)
    monkeypatch.setattr(job, "PARTIAL_OUT", partial_out)

    job.write_payload(
        {
            "source_count": 2,
            "debug_by_source": [
                complete_source("NLB"),
                failed_source("SAFRA"),
            ],
            "results": [],
        },
        review_store_at(tmp_path),
    )

    written = json.loads(out.read_text(encoding="utf-8"))
    partial = json.loads(partial_out.read_text(encoding="utf-8"))

    assert written["results"] == []
    assert written["partial"] is True
    assert partial["write_policy"] == "partial_collector_evidence"


def test_complete_collector_result_replaces_old_system_result(tmp_path, monkeypatch) -> None:
    out = tmp_path / "local_event_search_results.json"
    partial_out = tmp_path / "local_event_search_results.partial.json"
    out.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "title": "Old Event",
                        "when": future_label(),
                        "where": "Old Venue",
                        "url": "https://example.test/events/old",
                        "candidate_policy": VERIFIED_POLICY,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "OUT", out)
    monkeypatch.setattr(job, "PARTIAL_OUT", partial_out)

    new_event = {
        "title": "New Event",
        "when": future_label(),
        "where": "New Venue",
        "url": "https://example.test/events/new",
        "candidate_policy": VERIFIED_POLICY,
    }
    display = job.write_payload(
        {
            "source_count": 1,
            "debug_by_source": [complete_source("NLB")],
            "results": [new_event],
        },
        review_store_at(tmp_path),
    )

    assert [item["title"] for item in display["results"]] == ["New Event"]
    assert display["write_policy"] == "collector_complete_with_review"


def test_expired_event_is_removed_from_runtime_output() -> None:
    yesterday = date.today() - timedelta(days=1)
    payload = normalize_payload(
        {
            "results": [
                {
                    "title": "Expired Event",
                    "when": yesterday.isoformat(),
                    "start_date": yesterday.isoformat(),
                    "end_date": yesterday.isoformat(),
                    "url": "https://example.test/events/expired",
                    "candidate_policy": VERIFIED_POLICY,
                }
            ]
        }
    )

    assert payload["results"] == []
    assert payload["expired_events_removed"] == 1


def test_active_range_uses_when_end_when_end_date_field_is_missing() -> None:
    start = date.today() - timedelta(days=10)
    end = date.today() + timedelta(days=10)
    when = f"{start.day} {start.strftime('%b')} - {end.day} {end.strftime('%b')} {end.year}"
    payload = normalize_payload(
        {
            "results": [
                {
                    "title": "Active Exhibition",
                    "when": when,
                    "start_date": start.isoformat(),
                    "end_date": "",
                    "url": "https://example.test/events/active-exhibition",
                    "candidate_policy": VERIFIED_POLICY,
                }
            ]
        }
    )

    assert [item["title"] for item in payload["results"]] == ["Active Exhibition"]
    assert payload["expired_events_removed"] == 0
