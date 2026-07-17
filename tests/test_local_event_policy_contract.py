from __future__ import annotations

import json

from .conftest import SURFACE, read_text


def test_listing_authority_runtime_contract_is_active() -> None:
    job = read_text("surface/jobs/local_event_search.py")
    output = read_text("surface/local_events_runtime/output.py")
    config = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))

    assert job.index("apply_source_overrides()") < job.index("from local_events_runtime import collect_events")
    assert 'payload["extractor"] == "listing-authoritative-v52"' in job
    assert 'payload["version"] == 52' in job
    assert 'VERIFIED_POLICY = "official-listing-authority-v1"' in job
    assert 'VERIFIED_POLICY = "official-listing-authority-v1"' in output
    assert config["policy"]["listing_card_is_authoritative"] is True
    assert config["policy"]["unmatched_structured_records_are_rejected"] is True


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
