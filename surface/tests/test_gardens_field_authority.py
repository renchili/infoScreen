from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import extract  # noqa: E402
from local_events_runtime.gardens_field_authority import (  # noqa: E402
    apply_gardens_card_fields,
)


def test_gardens_timing_note_is_not_used_as_the_venue(monkeypatch) -> None:
    monkeypatch.setattr(extract, "TODAY", date(2026, 7, 22))
    source = {
        "id": "gardensbythebay",
        "name": "Gardens by the Bay",
        "default_venue": "Gardens by the Bay",
    }
    description = (
        "Experience the rich cultural traditions of Indonesia with ceremonial "
        "dance, Javanese calligraphy and hands-on activities."
    )
    card = {
        "link_text": "Orchid Extravaganza Cultural Programmes",
        "text": "\n".join(
            [
                "Orchid Extravaganza Cultural Programmes",
                description,
                "Sat, 25 Jul - Sun, 26 Jul 2026",
                "Various timings",
                "Flower Dome",
            ]
        ),
    }
    polluted = {
        "title": "Orchid Extravaganza Cultural Programmes",
        "when": "25 Jul - 26 Jul 2026",
        "where": "Various timings",
        "summary": description,
    }

    repaired = apply_gardens_card_fields(source, card, polluted)

    assert repaired["when"] == "25 Jul - 26 Jul 2026"
    assert repaired["where"] == "Flower Dome"


def test_gardens_authority_is_loaded_by_review_and_production() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")
    job = read_text("surface/jobs/local_event_search.py")

    assert "apply_gardens_field_authority()" in bootstrap
    assert "from local_events_runtime import gardens_field_authority" in job
    assert "gardens_field_authority.apply()" in job
