from __future__ import annotations

import re

import pytest

from .conftest import read_text

pytestmark = pytest.mark.style


def css_rule(css: str, selector: str) -> str:
    pattern = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>.*?)\}", re.DOTALL)
    for match in pattern.finditer(css):
        selectors = [part.strip() for part in match.group("selectors").split(",")]
        if selector in selectors:
            return match.group("body")
    raise AssertionError(f"missing CSS rule for {selector}")


def test_local_event_card_preserves_one_card_column_layout() -> None:
    css = read_text("surface/web/assets/css/local_events.css")
    body = css_rule(css, ".local-event-card")

    assert "display: flex" in body
    assert "flex-direction: column" in body
    assert "overflow: hidden" in body
    assert "height: 100%" in body


def test_local_event_source_toolbar_and_action_layout_are_not_overlapping() -> None:
    css = read_text("surface/web/assets/css/local_events.css")

    source = css_rule(css, ".local-event-source-top")
    toolbar = css_rule(css, ".local-event-toolbar")
    actions = css_rule(css, ".local-event-actions")

    assert "padding-right: 175px" in source
    assert "top: 8px" in toolbar and "right: 10px" in toolbar
    assert "margin-top: 6px" in actions
    assert "justify-content: flex-start" in actions


def test_local_event_description_uses_remaining_space_without_line_clamp() -> None:
    css = read_text("surface/web/assets/css/local_events.css")
    desc = css_rule(css, ".local-event-desc")

    assert "flex: 1 1 auto" in desc
    assert "display: block" in desc
    assert "-webkit-line-clamp" not in desc


def test_market_config_control_is_not_inside_quote_row_layout() -> None:
    css = read_text("surface/web/assets/css/market_custom.css")

    assert ".market-config-button" in css
    assert "position: absolute" in css
    assert "bottom:" in css
    assert ".market-row .market-config-button" not in css


def test_photo_wall_has_flip_card_layout() -> None:
    css = read_text("surface/web/assets/css/app.css") + "\n" + read_text("surface/web/assets/css/local_events.css")

    assert ".photo-flip-wall" in css
    assert ".photo-single-card" in css
    assert ".photo-single-inner" in css
