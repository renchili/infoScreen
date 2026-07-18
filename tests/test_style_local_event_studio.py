from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.style


def test_studio_layout_is_scrollable_and_responsive() -> None:
    css = read_text("surface/web/assets/css/local_event_studio.css")
    assert "min-height: 100vh" in css
    assert "overflow: hidden" not in css
    assert "@media (max-width: 1050px)" in css
    assert "@media (max-width: 680px)" in css
    assert "grid-template-columns: minmax(0, 1.65fr) minmax(350px, 0.85fr)" in css


def test_studio_canvas_and_image_share_one_overlay_stage() -> None:
    css = read_text("surface/web/assets/css/local_event_studio.css")
    assert ".image-stage" in css
    assert "position: relative" in css
    assert ".image-stage canvas" in css
    assert "position: absolute" in css
    assert "touch-action: none" in css


def test_studio_uses_project_visual_tokens_without_external_fonts() -> None:
    css = read_text("surface/web/assets/css/local_event_studio.css")
    for token in ["--bg", "--panel", "--line", "--text", "--muted", "--green", "--cyan", "--yellow", "--red"]:
        assert token in css
    assert "@import" not in css
    assert "url(" not in css
    assert "font-family" in css
