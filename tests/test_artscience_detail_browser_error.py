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


class ChromeErrorPage:
    url = "chrome-error://chromewebdata/"

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

    def wait_for_function(self, *args, **kwargs):
        raise AssertionError("an error page must be rejected before detail readiness")


def test_loaded_chrome_error_page_records_real_navigation_failure() -> None:
    with pytest.raises(RuntimeError) as raised:
        artscience_detail.read_loaded_detail_candidate(
            ChromeErrorPage(),
            {"default_venue": "ArtScience Museum"},
            LISTING_URL,
            DETAIL_URL,
        )

    error = str(raised.value)
    assert "browser_error_page" in error
    assert "error_code=ERR_HTTP2_PROTOCOL_ERROR" in error
    assert "title=This site can’t be reached" in error
    assert "page_url=chrome-error://chromewebdata/" in error
    assert f"requested_url={DETAIL_URL}" in error


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
            "RuntimeError: browser_error_page; "
            "error_code=ERR_HTTP2_PROTOCOL_ERROR; "
            "title=This site can’t be reached"
        ),
    )

    assert detail["title"] == "Another World Is Possible"
    assert detail["detail_status"] == "failed"
    assert detail["detail_page_title"] == ""
    assert "ERR_HTTP2_PROTOCOL_ERROR" in detail["detail_error"]
    assert "This site can’t be reached" in detail["detail_error"]
