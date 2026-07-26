from __future__ import annotations

import os
import sys
from pathlib import Path

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import http1_browser  # noqa: E402


def test_navigation_commits_once_and_accepts_a_readable_document() -> None:
    authority = read_text(
        "surface/local_events_runtime/resilient_navigation_authority.py"
    )

    assert 'commit_kwargs["wait_until"] = "commit"' in authority
    assert "READABLE_DOCUMENT_JS" in authority
    assert 'page.wait_for_function(READABLE_DOCUMENT_JS' in authority
    assert 'page.wait_for_load_state("domcontentloaded"' in authority
    assert 'page.wait_for_load_state(\n                "networkidle"' in authority
    assert "if _document_readable(page):" in authority
    assert "Page.goto = _goto_with_readable_document" in authority


def test_navigation_does_not_turn_a_readable_page_into_a_timeout() -> None:
    authority = read_text(
        "surface/local_events_runtime/resilient_navigation_authority.py"
    )

    readable_fallback = authority.index("if _document_readable(page):")
    first_raise = authority.index("raise", readable_fallback)

    assert readable_fallback < first_raise
    assert "Repeating ``goto`` starts the same slow navigation again" in authority


def test_navigation_authority_is_installed_before_browser_launch() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    navigation = bootstrap.index("apply_navigation()")
    executable = bootstrap.index("executable = _find_supported_browser_executable()")
    chromium_launch = bootstrap.index("playwright.chromium.launch(")

    assert navigation < executable < chromium_launch


def test_snap_chromium_is_never_a_supported_browser() -> None:
    assert http1_browser._is_snap_browser("/snap/bin/chromium") is True
    assert (
        http1_browser._is_snap_browser("/var/lib/snapd/snap/bin/chromium")
        is True
    )
    assert http1_browser._is_snap_browser("/usr/bin/google-chrome") is False


def test_browser_selection_skips_snap_and_uses_normal_executable(tmp_path: Path) -> None:
    browser = tmp_path / "google-chrome"
    browser.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    browser.chmod(browser.stat().st_mode | 0o111)

    selected = http1_browser._select_browser_executable(
        ["/snap/bin/chromium", str(browser)]
    )

    assert selected == str(browser)
    assert os.access(selected, os.X_OK)
