from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import acm_primary_fact_sequence_authority as authority  # noqa: E402


FACTS = {
    "date": "10–12 April 2026",
    "time": "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm",
    "venue": "Asian Civilisations Museum",
    "admission": "Free and ticketed activities available",
}


def test_acm_visual_fact_script_preserves_four_separate_rows() -> None:
    script = authority._wrap_script("() => ({title: 'Activity', lines: []})")

    assert authority._MARKER in script
    assert "getBoundingClientRect" in script
    assert "compareDocumentPosition" not in script
    assert 'add("Date")' in script
    assert 'add("Time")' in script
    assert 'add("Location")' in script
    assert 'add("Admission")' in script
    assert "primary_facts: facts" in script
    assert "dates: [when]" in script
    assert "venues: [facts.venue]" in script


def test_browser_merge_preserves_primary_fact_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_BROWSER_MERGE",
        lambda card, detail: {"title": "Activity"},
    )

    merged = authority.merge_detail_payload({}, {"primary_facts": FACTS})

    assert merged["detail_primary_facts"] == FACTS
    assert merged["detail_dates"] == [
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    ]
    assert merged["detail_venues"] == ["Asian Civilisations Museum"]


def test_formal_collector_preserves_primary_fact_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_SOURCE_MERGE",
        lambda source, card, payload, index: {"detail_evidence": {"title": "Activity"}},
    )

    merged = authority.merge_source_detail(
        {"id": "acm"},
        {},
        {"primary_facts": FACTS},
        0,
    )

    evidence = merged["detail_evidence"]
    assert evidence["primary_facts"] == FACTS
    assert evidence["date_candidates"] == [
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    ]
    assert evidence["venue_candidates"] == ["Asian Civilisations Museum"]


def test_final_when_and_venue_come_from_preserved_parent_facts(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_PICK_WHEN",
        lambda card: ("Daily - Friday, 5–9.30pm", "listing fallback"),
    )
    monkeypatch.setattr(
        authority,
        "_BASE_PICK_VENUE",
        lambda source, card, when, when_line: "River Room",
    )
    card = {"detail_primary_facts": FACTS}

    when, source_line = authority.pick_when(card)
    venue = authority.pick_venue(
        {"name": "Asian Civilisations Museum"},
        card,
        when,
        source_line,
    )

    expected = (
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    )
    assert when == expected
    assert source_line == expected
    assert venue == "Asian Civilisations Museum"


def test_acm_fact_sequence_is_bound_before_final_review_snapshot() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    generic = bootstrap.index("apply_open_detail_fields_authority()")
    acm = bootstrap.index("apply_acm_primary_fact_sequence_authority()")
    gardens = bootstrap.index("apply_gardens_field_authority()")
    binding = bootstrap.index("_bind_final_browser_runtime_to_review()")

    assert generic < acm < gardens < binding
