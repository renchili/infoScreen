from __future__ import annotations

import sys

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import artscience_detail  # noqa: E402
from local_events_runtime import preview_direct_detail_collector_authority as collector  # noqa: E402


LISTING_URL = (
    "https://www.marinabaysands.com/museum/about-us/exhibition-archive.html"
)
DETAIL_URL = (
    "https://www.marinabaysands.com/museum/exhibitions/"
    "another-world-is-possible.html"
)


class PersistentChromeErrorPage:
    url = "chrome-error://chromewebdata/"

    def __init__(self) -> None:
        self.waited = False

    def evaluate(self, script):
        assert script == artscience_detail.ARTSCIENCE_BROWSER_ERROR_JS
        return {
            "is_error": True,
            "url": self.url,
            "title": "This site can’t be reached",
            "error_code": "ERR_HTTP2_PROTOCOL_ERROR",
            "body": (
                "This site can’t be reached. The webpage at the requested address "
                "might be temporarily down. ERR_HTTP2_PROTOCOL_ERROR"
            ),
        }

    def title(self):
        return "This site can’t be reached"

    def wait_for_function(self, script, **kwargs):
        assert script == artscience_detail.ARTSCIENCE_DETAIL_READY_JS
        self.waited = True
        raise TimeoutError("detail page did not become ready")


class TransientChromeErrorPage:
    def __init__(self) -> None:
        self.url = "chrome-error://chromewebdata/"
        self.recovered = False

    def wait_for_function(self, script, **kwargs):
        assert script == artscience_detail.ARTSCIENCE_DETAIL_READY_JS
        self.recovered = True
        self.url = DETAIL_URL

    def evaluate(self, script):
        assert self.recovered is True
        if script == artscience_detail.ARTSCIENCE_BROWSER_ERROR_JS:
            return {
                "is_error": False,
                "url": DETAIL_URL,
                "title": "Another World Is Possible",
                "error_code": "",
                "body": "Another World Is Possible Exhibition Details",
            }
        assert script == artscience_detail.ARTSCIENCE_DETAIL_FIELDS_JS
        return {
            "title": "Another World Is Possible",
            "when": "13 Sep 2025 – 22 Feb 2026",
            "where": "ArtScience Museum",
            "summary": "Official exhibition details.",
            "detail_page_title": "Another World Is Possible",
        }

    def title(self):
        return "Another World Is Possible"


def test_persistent_chrome_error_page_is_checked_only_after_wait() -> None:
    page = PersistentChromeErrorPage()

    with pytest.raises(RuntimeError) as raised:
        artscience_detail.read_loaded_detail_candidate(
            page,
            {"default_venue": "ArtScience Museum"},
            LISTING_URL,
            DETAIL_URL,
        )

    assert page.waited is True
    error = str(raised.value)
    assert "detail_page_not_ready_after_wait" in error
    assert "observed_browser_error_page" in error
    assert "observed_code=ERR_HTTP2_PROTOCOL_ERROR" in error
    assert "observed_title=This site can’t be reached" in error
    assert "observed_page_url=chrome-error://chromewebdata/" in error
    assert f"requested_url={DETAIL_URL}" in error


def test_transient_chrome_error_page_can_recover_to_real_detail() -> None:
    result = artscience_detail.read_loaded_detail_candidate(
        TransientChromeErrorPage(),
        {"default_venue": "ArtScience Museum"},
        LISTING_URL,
        DETAIL_URL,
    )

    assert result["title"] == "Another World Is Possible"
    assert result["when"] == "13 Sep 2025 – 22 Feb 2026"
    assert result["detail_status"] == "collected"
    assert result["detail_error"] == ""


def test_failed_detail_keeps_listing_event_identity() -> None:
    detail = collector._failed_detail(
        {
            "detail_url": DETAIL_URL,
            "title": "Another World Is Possible",
            "when": "",
            "where": "",
            "summary": "",
        },
        "ArtScience Museum",
        (
            "RuntimeError: detail_page_not_ready_after_wait; "
            "observed_browser_error_page; "
            "observed_code=ERR_HTTP2_PROTOCOL_ERROR; "
            "observed_title=This site can’t be reached"
        ),
    )

    assert detail["title"] == "Another World Is Possible"
    assert detail["detail_status"] == "failed"
    assert detail["detail_page_title"] == ""
    assert "ERR_HTTP2_PROTOCOL_ERROR" in detail["detail_error"]
    assert "This site can’t be reached" in detail["detail_error"]
