from __future__ import annotations

import sys
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_payload_authority  # noqa: E402
from local_events_runtime import review_detail_navigation_authority as authority  # noqa: E402
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


detail_payload_authority.apply()


class FakePage:
    def __init__(self) -> None:
        self.url = "https://www.acm.nhb.gov.sg/whats-on/exhibitions/crosscurrents"
        self.goto_calls: list[dict[str, object]] = []
        self.closed = False

    def goto(self, url: str, **kwargs):
        self.url = url
        self.goto_calls.append({"url": url, **kwargs})
        return SimpleNamespace(status=200)

    def wait_for_function(self, script: str, timeout: int) -> None:
        assert "document.body" in script
        assert timeout == authority.DETAIL_CONTENT_WAIT_MS

    def wait_for_timeout(self, milliseconds: int) -> None:
        assert milliseconds == 150

    def evaluate(self, script: str):
        assert "itemprop='startDate'" in script
        return {
            "title": "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre",
            "dates": ["19 Jun 2026 – 24 Jan 2027"],
            "venues": ["Islamic Art Gallery, Level 2 and Design Gallery, Level 3"],
            "summary": "This exhibition presents one hundred masterpieces from the Louvre.",
            "lines": [],
            "headings": [
                "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre"
            ],
            "canonical": self.url,
            "eventObjects": [],
        }

    def title(self) -> str:
        return "Crosscurrents"

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()

    def new_page(self) -> FakePage:
        return self.page


class NoDetailContext:
    def new_page(self):
        raise AssertionError("complete listing card must not open a detail page")


def test_review_detail_read_is_blocking_but_does_not_wait_for_lifecycle_idle() -> None:
    context = FakeContext()
    source = {
        "id": "acm",
        "name": "Asian Civilisations Museum",
        "default_venue": "Asian Civilisations Museum",
        "review_detail_policy": "always",
    }
    listing_url = "https://www.acm.nhb.gov.sg/whats-on/overview"
    detail_url = context.page.url
    card = {
        "id": "acm-crosscurrents",
        "url": detail_url,
        "headings": ["Crosscurrents"],
        "link_text": "Crosscurrents",
        "text": "Crosscurrents",
        "text_lines": ["Crosscurrents"],
        "extraction_mode": "detail_link",
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": listing_url,
        "listing_card_id": "acm-crosscurrents",
    }

    result = authority._detail_candidate(
        context,
        source,
        listing_url,
        detail_url,
        card,
    )

    assert context.page.goto_calls == [
        {
            "url": detail_url,
            "wait_until": "commit",
            "timeout": authority.DETAIL_COMMIT_TIMEOUT_MS,
        }
    ]
    assert result["detail_status"] == "collected"
    assert result["when"] == "19 Jun 2026 – 24 Jan 2027"
    assert result["where"] == "Islamic Art Gallery, Level 2 and Design Gallery, Level 3"
    assert result["summary"].startswith("This exhibition presents")
    assert context.page.closed is True


def test_complete_authoritative_listing_card_does_not_open_detail_page() -> None:
    listing_url = "https://www.thekallang.com.sg/en/things-to-do/events.html"
    detail_url = "https://www.thekallang.com.sg/en/events/example-event"
    source = {
        "id": "thekallang",
        "name": "The Kallang",
        "default_venue": "The Kallang",
    }
    card = {
        "id": "thekallang-example-event",
        "url": detail_url,
        "headings": ["Example Event"],
        "link_text": "Example Event",
        "text": "Example Event\n19 Jun 2026\nThe Kallang",
        "text_lines": ["Example Event", "19 Jun 2026", "The Kallang"],
        "extraction_mode": "detail_link",
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": listing_url,
        "listing_card_id": "thekallang-example-event",
    }

    result = authority._detail_candidate(
        NoDetailContext(),
        source,
        listing_url,
        detail_url,
        card,
    )

    assert result == {
        "detail_url": detail_url,
        "title": "Example Event",
        "when": "19 Jun 2026",
        "where": "The Kallang",
        "summary": "",
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "",
    }


def test_fallback_fills_summary_without_appending_child_fields() -> None:
    parent_when = (
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    )
    result = authority._merge_fallback_fields(
        {
            "dates": [parent_when],
            "venues": ["Asian Civilisations Museum"],
            "summary": "",
        },
        {
            "dates": ["12 April 2026"],
            "venues": ["River Room"],
            "summary": "A weekend programme of activities throughout the museum.",
        },
    )

    assert result["dates"] == [parent_when]
    assert result["venues"] == ["Asian Civilisations Museum"]
    assert result["summary"].startswith("A weekend programme")


def test_unlabelled_acm_fact_lines_are_preserved_verbatim() -> None:
    payload = {
        "dates": [],
        "venues": [],
        "lines": [
            "LIGHT TO NIGHT AT ACM: POWER OF PLAY",
            "Programme",
            "Experience ACM after dark through the Power of Play!",
            "Programmes on 23, 24, 30, 31 Jan 2026, 6–10pm",
            "Asian Civilisations Museum",
            "5 mins walk from Raffles Place MRT (Exit H), More Info",
            "Free admission to most activities",
            "Visit Asian Civilisations Museum today",
            "BOOK YOUR TICKET NOW",
        ],
    }

    assert authority._raw_when(payload) == (
        "Programmes on 23, 24, 30, 31 Jan 2026, 6–10pm"
    )
    assert authority._raw_where(payload) == "Asian Civilisations Museum"


def test_review_ui_still_blocks_collect_events_request() -> None:
    blocker = read_text("surface/web/assets/js/local_event_review_blocking.js")
    studio = read_text("surface/web/local-events/studio/index.html")

    assert '"/api/local-events/review/collect-events"' in blocker
    assert "local_event_review_jobs.js" not in studio
    assert "Do not close or reload this page" in blocker


def test_bounded_detail_authority_is_installed_before_diagnostic_collector() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    payload = bootstrap.index("apply_detail_payload_authority()")
    detail = bootstrap.index("apply_review_detail_navigation_authority()")
    diagnostics = bootstrap.index("apply_event_review_diagnostics()")

    assert payload < detail < diagnostics
    assert "apply_async_collection" not in bootstrap


def test_detail_navigation_has_no_networkidle_or_domcontentloaded_wait() -> None:
    code = read_text(
        "surface/local_events_runtime/review_detail_navigation_authority.py"
    )

    assert 'wait_until="commit"' in code
    assert 'wait_until="networkidle"' not in code
    assert 'wait_until="domcontentloaded"' not in code
    assert "DETAIL_CONTENT_WAIT_MS = 12_000" in code
