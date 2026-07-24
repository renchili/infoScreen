from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime.output import normalize_payload  # noqa: E402


def test_structured_first_runtime_contract_is_active() -> None:
    job = read_text("surface/jobs/local_event_search.py")
    output = read_text("surface/local_events_runtime/output.py")

    assert "apply_source_overrides()" not in job
    assert "apply_listing_url_authority()" not in job
    assert "apply_detail_authority()" not in job
    assert 'payload["extractor"] == "structured-first-v49-source-order"' in job
    assert 'payload["version"] == 49' in job
    assert 'extractor.startswith("structured-first")' in output


def test_structured_first_result_without_listing_policy_survives_output() -> None:
    tomorrow = date.today() + timedelta(days=1)
    payload = normalize_payload(
        {
            "extractor": "structured-first-v49-source-order",
            "results": [
                {
                    "title": "Current Official Event",
                    "when": tomorrow.isoformat(),
                    "start_date": tomorrow.isoformat(),
                    "end_date": tomorrow.isoformat(),
                    "where": "Official Venue",
                    "url": "https://example.org/events/current-official-event",
                }
            ],
        }
    )

    assert [item["title"] for item in payload["results"]] == ["Current Official Event"]
    assert payload["invalid_events_removed"] == 0


def test_reported_dynamic_sources_remain_in_official_inventory() -> None:
    config = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in config["sources"]}

    assert "https://www.nationalgallery.sg/sg/en/whats-on.html" in sources["nationalgallery"]["listing_urls"]
    assert "https://www.nationalmuseum.nhb.gov.sg/whats-on/view-all" in sources["nationalmuseum"]["listing_urls"]
    assert "https://www.sentosa.com.sg/en/things-to-do/events/" in sources["sentosa"]["listing_urls"]
    assert "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events.html" in sources["gardensbythebay"]["listing_urls"]
    assert {
        "https://www.science.edu.sg/whats-on/workshops-activities",
        "https://www.science.edu.sg/whats-on/exhibitions",
        "https://www.science.edu.sg/whats-on/shows-demonstrations",
        "https://www.science.edu.sg/whats-on",
    } <= set(sources["sciencecentre"]["listing_urls"])
