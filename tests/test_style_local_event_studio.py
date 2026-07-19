from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.style


def test_live_studio_layout_is_scrollable_and_responsive() -> None:
    css = read_text("surface/web/assets/css/local_event_studio.css")
    assert "overflow:hidden" not in css.replace(" ", "")
    for selector in [
        ".shell",
        ".panel",
        ".grid",
        ".rule-grid",
        ".metrics",
        ".columns",
        ".results",
    ]:
        assert selector in css
    assert "@media(max-width:1000px)" in css.replace(" ", "")
    assert "@media(max-width:650px)" in css.replace(" ", "")


def test_live_studio_has_no_screenshot_or_canvas_stage() -> None:
    css = read_text("surface/web/assets/css/local_event_studio.css")
    assert ".image-stage" not in css
    assert "canvas" not in css
    assert "touch-action" not in css


def test_studio_uses_project_visual_tokens_without_external_fonts() -> None:
    css = read_text("surface/web/assets/css/local_event_studio.css")
    for token in [
        "--bg",
        "--panel",
        "--line",
        "--text",
        "--muted",
        "--green",
        "--cyan",
        "--yellow",
        "--red",
    ]:
        assert token in css
    assert "@import" not in css
    assert "url(" not in css
    assert "font-family" in css
