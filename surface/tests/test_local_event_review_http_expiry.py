from __future__ import annotations

import sys
from types import SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import http1_browser  # noqa: E402
from local_events_runtime import review_effective_fields_authority as authority  # noqa: E402


def _state(when: str):
    return SimpleNamespace(
        events=[SimpleNamespace(when=when)],
        event_collection={"candidate_count": 1, "expired_candidate_count": 0},
    )


def test_final_http_handoff_expires_same_month_past_range() -> None:
    when = "Daily – 8–9 Mar 2025, 1–7pm"

    assert [value.isoformat() for value in authority._line_dates(when)] == [
        "2025-03-08",
        "2025-03-09",
    ]

    state = http1_browser._filter_final_expired_events(_state(when), authority)

    assert state.events == []
    assert state.event_collection["candidate_count"] == 0
    assert state.event_collection["expired_candidate_count"] == 1


def test_final_http_handoff_preserves_existing_from_schedule_policy() -> None:
    state = http1_browser._filter_final_expired_events(
        _state("From 24 March 2023 · Daily – 10am – 7pm"),
        authority,
    )

    assert len(state.events) == 1
    assert state.event_collection["candidate_count"] == 1
    assert state.event_collection["expired_candidate_count"] == 0
