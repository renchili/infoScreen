from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime.output import normalize_payload, plain_text  # noqa: E402


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


def test_local_event_payload_is_normalized_before_runtime_delivery() -> None:
    payload = {
        "results": [
            {
                "title": "What Happens After Someone Dies: A Practical Guide for Families",
                "when": "July 14, 2026",
                "where": "<span>Central Public Library</span>",
                "summary": (
                    '<p><strong>About the Event</strong></p>'
                    '<p>This talk is a compassionate and practical guide to navigating loss.</p>'
                ),
                "url": "https://example.test/event?a=1&b=2",
            }
        ]
    }

    normalized = normalize_payload(payload)
    event = normalized["results"][0]

    assert event["where"] == "Central Public Library"
    assert event["summary"] == "This talk is a compassionate and practical guide to navigating loss."
    assert "<" not in event["summary"]
    assert event["url"] == "https://example.test/event?a=1&b=2"
    assert normalized["text_normalizer"] == "plain-text-v1"
    assert normalized["normalized_text_fields"] == 2


def test_local_event_payload_promotes_venue_alias_to_where() -> None:
    normalized = normalize_payload(
        {
            "results": [
                {
                    "title": "Example Event",
                    "when": "1 Aug 2026",
                    "where": "",
                    "venue": "NLB Building, Level 1",
                    "summary": "Details",
                }
            ]
        }
    )

    assert normalized["results"][0]["where"] == "NLB Building, Level 1"
