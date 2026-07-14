from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.frontend


def test_local_event_frontend_reads_canonical_where_field_first() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert 'var where = pick(row, ["where", "venue", "place", "where_text", "location", "address"]);' in js


def test_local_event_frontend_reads_canonical_summary_field_first() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert 'var summary = pick(row, ["summary", "why_text", "description", "desc"]);' in js


def test_local_event_frontend_keeps_text_cleanup_out_of_rendering() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert "DOMParser" not in js
    assert "stripHTML" not in js


def test_local_event_details_are_fitted_against_the_rendered_height() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert "function fitDescription()" in js
    assert "desc.scrollHeight <= desc.clientHeight" in js
    assert "desc.dataset.fullText" in js
    assert 'desc.textContent = fitted + "…"' in js
    assert "scheduleDescriptionFit()" in js
    assert 'window.addEventListener("resize", scheduleDescriptionFit)' in js


def test_local_event_details_use_full_text_before_measured_fitting() -> None:
    js = read_text("surface/web/assets/js/local_event_card.js")

    assert "short(x.summary, 900)" not in js
    assert "esc(x.summary)" in js
    assert "desc.dataset.fullText = x.summary" in js
