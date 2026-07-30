from __future__ import annotations

import sys
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import artscience_detail as detail  # noqa: E402


LISTING_URL = (
    "https://www.marinabaysands.com/museum/about-us/exhibition-archive.html"
)
DETAIL_URL = (
    "https://www.marinabaysands.com/museum/exhibitions/"
    "another-world-is-possible.html"
)


class Page:
    def __init__(self, payload):
        self.payload = payload
        self.url = DETAIL_URL
        self.goto_calls = []
        self.wait_calls = []

    def goto(self, url, *, wait_until, timeout):
        self.goto_calls.append((url, wait_until, timeout))
        return SimpleNamespace(status=200)

    def wait_for_function(self, script, *, timeout):
        self.wait_calls.append((script, timeout))

    def evaluate(self, script):
        assert script == detail.ARTSCIENCE_DETAIL_FIELDS_JS
        return self.payload

    def title(self):
        return "Another World Is Possible | ArtScience Museum"


def test_artscience_detail_keeps_exact_schedule_and_source_venue() -> None:
    page = Page(
        {
            "title": "Another World Is Possible",
            "when": "13 Sep 2025 – 22 Feb 2026",
            "where": "",
            "summary": "An exhibition on the future and world-building.",
            "detail_page_title": "Another World Is Possible",
        }
    )

    result = detail.collect_detail_candidate(
        page,
        {
            "id": "artscience",
            "default_venue": "ArtScience Museum",
        },
        LISTING_URL,
        DETAIL_URL,
    )

    assert page.goto_calls == [
        (DETAIL_URL, "commit", detail._detail_navigation.DETAIL_COMMIT_TIMEOUT_MS)
    ]
    assert result == {
        "detail_url": DETAIL_URL,
        "title": "Another World Is Possible",
        "when": "13 Sep 2025 – 22 Feb 2026",
        "where": "ArtScience Museum",
        "summary": "An exhibition on the future and world-building.",
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "Another World Is Possible",
    }


def test_artscience_detail_reports_missing_schedule_without_inventing_one() -> None:
    page = Page(
        {
            "title": "Another World Is Possible",
            "when": "",
            "where": "",
            "summary": "An exhibition on the future and world-building.",
            "detail_page_title": "Another World Is Possible",
        }
    )

    result = detail.collect_detail_candidate(
        page,
        {
            "id": "artscience",
            "default_venue": "ArtScience Museum",
        },
        LISTING_URL,
        DETAIL_URL,
    )

    assert result["when"] == ""
    assert result["where"] == "ArtScience Museum"
    assert result["detail_status"] == "incomplete"
    assert result["detail_error"] == "missing_detail_when"


def test_artscience_detail_script_is_bounded_to_the_activity_details_block() -> None:
    source = read_text("surface/local_events_runtime/artscience_detail.py")
    script = detail.ARTSCIENCE_DETAIL_FIELDS_JS.lower()

    assert "exhibition|event|programme|program|experience" in script
    assert "details" in script
    assert "fullrange" in script
    assert "facts = lines.slice" in script
    assert "default_venue" in source
    assert "another world is possible" not in source.lower()
    assert "13 sep 2025" not in source.lower()
