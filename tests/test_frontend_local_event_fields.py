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
