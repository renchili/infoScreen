from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import acm_primary_fact_sequence_authority as authority  # noqa: E402
from local_events_runtime import review_detail_navigation_authority as navigation  # noqa: E402


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


class _FakeDetailPage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.closed = False

    def goto(self, url: str, **_: object) -> None:
        self.url = url
        return None

    def wait_for_function(self, *_: object, **__: object) -> None:
        return None

    def wait_for_timeout(self, *_: object, **__: object) -> None:
        return None

    def evaluate(self, script: str) -> dict:
        assert script == navigation._browser.DETAIL_CARD_JS
        return {
            "title": "Crossing Cultures at ACM: A Weekend of Curiosities",
            "dates": [
                "10–12 April 2026 · "
                "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
            ],
            "venues": ["Asian Civilisations Museum"],
            "primary_facts": FACTS,
            "summary": (
                "Explore a weekend programme of installations, performances, "
                "workshops and activities at ACM."
            ),
        }

    def title(self) -> str:
        return "Crossing Cultures at ACM: A Weekend of Curiosities"

    def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, url: str) -> None:
        self.page = _FakeDetailPage(url)

    def new_page(self) -> _FakeDetailPage:
        return self.page


def test_past_date_rejection_keeps_final_parent_fields(monkeypatch) -> None:
    expected_when = (
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    )
    detail_url = (
        "https://www.acm.nhb.gov.sg/whats-on/programmes/"
        "cc-weekend-of-curiosities"
    )
    context = _FakeContext(detail_url)

    monkeypatch.setattr(
        navigation._provenance,
        "listing_detail_url",
        lambda listing_url, raw_url: raw_url,
    )
    monkeypatch.setattr(
        navigation._browser,
        "merge_detail_payload",
        lambda card, payload: {
            **card,
            "detail_primary_facts": FACTS,
            "detail_dates": [expected_when],
            "detail_venues": ["Asian Civilisations Museum"],
        },
    )
    monkeypatch.setattr(
        navigation._extract,
        "event_from_card",
        lambda source, merged: (None, "past_date"),
    )
    monkeypatch.setattr(
        navigation._extract,
        "pick_when",
        lambda merged: (expected_when, expected_when),
    )
    monkeypatch.setattr(
        navigation._extract,
        "pick_venue",
        lambda source, merged, when, when_line: "Asian Civilisations Museum",
    )
    monkeypatch.setattr(
        navigation._detail_dates,
        "_listing_fields",
        lambda source, card: {
            "title": "Crossing Cultures at ACM: A Weekend of Curiosities",
            "when": "Daily - Friday, 5–9.30pm",
            "where": "River Room",
            "summary": "Listing fallback summary",
        },
    )

    result = navigation._detail_candidate(
        context,
        {"id": "acm", "name": "Asian Civilisations Museum"},
        "https://www.acm.nhb.gov.sg/whats-on/overview",
        detail_url,
        {"text": "listing card"},
    )

    assert result["detail_status"] == "incomplete"
    assert result["detail_error"] == "past_date"
    assert result["when"] == expected_when
    assert result["where"] == "Asian Civilisations Museum"
    assert result["when"] != "Daily - Friday, 5–9.30pm"
    assert result["where"] != "River Room"
    assert context.page.closed is True
