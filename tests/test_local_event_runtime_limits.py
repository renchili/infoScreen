from __future__ import annotations

from .conftest import read_text


def test_job_detail_budget_matches_total_event_budget() -> None:
    script = read_text("surface/jobs/local_event_search.py")

    assert 'LOCAL_EVENTS_DETAIL_LIMIT", "6"' not in script
    assert 'os.environ["LOCAL_EVENTS_MAX_TOTAL_EVENTS"]' in script
    assert 'LOCAL_EVENTS_DETAIL_TIMEOUT_MS", "60000"' in script
    assert 'LOCAL_EVENTS_MAX_SECONDS", "900"' in script
    assert 'LOCAL_EVENTS_SOURCE_TIMEOUT_SECONDS", "780"' in script
