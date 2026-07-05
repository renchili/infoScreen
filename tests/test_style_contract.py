from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.style


def test_local_event_card_preserves_one_card_column_layout() -> None:
    css = read_text("surface/web/assets/css/local_events.css")

    assert ".local-event-card" in css
    assert "display: flex" in css
    assert "flex-direction: column" in css
    assert "overflow: hidden" in css
    assert "height: 100%" in css


def test_local_event_source_toolbar_and_action_layout_are_not_overlapping() -> None:
    css = read_text("surface/web/assets/css/local_events.css")

    assert ".local-event-source-top" in css
    assert ".local-event-toolbar" in css
    assert ".local-event-actions" in css
    assert "padding-right: 175px" in css
    assert "top: 8px" in css
    assert "right: 10px" in css
    assert "margin-top: 6px" in css
    assert "justify-content: flex-start" in css


def test_local_event_description_uses_remaining_space_without_line_clamp() -> None:
    css = read_text("surface/web/assets/css/local_events.css")
    desc_start = css.index(".local-event-desc {")
    desc_end = css.index("}", desc_start)
    desc = css[desc_start:desc_end]

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
