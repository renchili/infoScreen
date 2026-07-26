from __future__ import annotations

from .conftest import read_text


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
    executable = bootstrap.index("executable = original_find()")
    chromium_launch = bootstrap.index("playwright.chromium.launch(")

    assert navigation < executable < chromium_launch
