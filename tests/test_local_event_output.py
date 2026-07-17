from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from jobs import local_event_search as job  # noqa: E402
from local_events_runtime.output import normalize_payload, plain_text  # noqa: E402

VERIFIED_POLICY = "official-listing-authority-v1"


def future_label(days: int = 30) -> str:
    value = date.today() + timedelta(days=days)
    return f"{value.day} {value.strftime('%b')} {value.year}"


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
    assert event["summary"] == "This talk is a compassionate and practical guide to navigating loss."
    assert "<" not in event["summary"]
    assert event["url"] == "https://example.test/events/practical-guide"
    assert normalized["text_normalizer"] == "plain-text-v1"
    assert normalized["normalized_text_fields"] == 2


def test_description_alias_is_cleaned_and_promoted_to_summary() -> None:
    payload = {
        "results": [
            {
                "title": "What Happens After Someone Dies: A Practical Guide for Families",
                "when": future_label(),
                "where": "Central Public Library",
                "description": (
                    '<p><strong>About the Event</strong><span style="background-color:#00ffff;"></span></p>'
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
    assert "<" not in event["description"]
    assert "<" not in event["summary"]


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


def test_partial_refresh_cleans_the_verified_result_it_keeps(tmp_path, monkeypatch) -> None:
    out = tmp_path / "local_event_search_results.json"
    partial_out = tmp_path / "local_event_search_results.partial.json"
    out.write_text(
        json.dumps(
            {
                "source_count": 1,
                "debug_by_source": [{"source": "NLB"}],
                "results": [
                    {
                        "title": "What Happens After Someone Dies: A Practical Guide for Families",
                        "when": future_label(),
                        "where": "Central Public Library",
                        "url": "https://example.test/events/practical-guide",
                        "candidate_policy": VERIFIED_POLICY,
                        "description": (
                            '<p><strong>About the Event</strong></p>'
                            '<p>This talk is a compassionate and practical guide to navigating loss.</p>'
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "OUT", out)
    monkeypatch.setattr(job, "PARTIAL_OUT", partial_out)

    job.write_payload(
        {
            "source_count": 2,
            "debug_by_source": [{"source": "NLB"}],
            "results": [],
        }
    )

    retained = json.loads(out.read_text(encoding="utf-8"))
    retained_event = retained["results"][0]
    partial = json.loads(partial_out.read_text(encoding="utf-8"))

    expected = "This talk is a compassionate and practical guide to navigating loss."
    assert retained_event["summary"] == expected
    assert retained_event["description"] == expected
    assert "<" not in retained_event["summary"]
    assert retained["text_normalizer"] == "plain-text-v1"
    assert partial["write_policy"] == "kept_previous_verified_result"


def test_unverified_legacy_rows_are_not_preserved_during_partial_refresh(tmp_path, monkeypatch) -> None:
    out = tmp_path / "local_event_search_results.json"
    partial_out = tmp_path / "local_event_search_results.partial.json"
    out.write_text(
        json.dumps(
            {
                "source_count": 1,
                "debug_by_source": [{"source": "SAFRA"}],
                "results": [
                    {
                        "title": "Carpark",
                        "when": future_label(),
                        "where": "SAFRA Clubs",
                        "url": "https://example.test/amenities/carpark",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "OUT", out)
    monkeypatch.setattr(job, "PARTIAL_OUT", partial_out)

    job.write_payload(
        {
            "source_count": 2,
            "debug_by_source": [{"source": "SAFRA"}],
            "results": [],
        }
    )

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["results"] == []
    assert written["partial"] is True
    assert not partial_out.exists()


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
