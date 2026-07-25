from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.style


def test_dashboard_left_column_allocates_all_three_panels() -> None:
    html = read_text("surface/web/index.html")
    layout = read_text("surface/web/assets/css/dashboard_layout.css")

    left_start = html.index('<section class="col left">')
    left_end = html.index("</section>", left_start)
    left = html[left_start:left_end]
    assert left.count('class="box') == 3
    assert "assets/css/dashboard_layout.css" in html
    assert (
        "grid-template-rows: minmax(0, 1fr) minmax(0, 1.25fr) 46px"
        in layout
    )


def test_dashboard_quiet_background_override_disables_scanline_overlay() -> None:
    layout = read_text("surface/web/assets/css/dashboard_layout.css")

    assert "body::before" in layout
    assert "display: none !important" in layout
    assert "repeating-linear-gradient" not in layout


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


def test_local_event_description_is_contained_in_remaining_card_space() -> None:
    css = read_text("surface/web/assets/css/local_events.css")
    desc_start = css.index(".local-event-desc {")
    desc_end = css.index("}", desc_start)
    desc = css[desc_start:desc_end]

    assert "flex: 1 1 0" in desc
    assert "min-height: 0" in desc
    assert "max-width: 100%" in desc
    assert "max-height: 100%" in desc
    assert "overflow: hidden" in desc
    assert "overflow-wrap: anywhere" in desc
    assert "word-break: break-word" in desc
    assert "white-space: normal" in desc
    assert "contain: paint" in desc


def test_local_event_title_and_metadata_wrap_unbroken_content() -> None:
    css = read_text("surface/web/assets/css/local_events.css")

    assert css.count("overflow-wrap: anywhere") >= 3
    assert css.count("word-break: break-word") >= 3
    assert ".local-event-kv" in css
    assert "overflow: hidden" in css


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
