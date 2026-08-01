from __future__ import annotations

import sys

import pytest

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import deadline_authority as authority  # noqa: E402


class FakePage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def goto(self, *args, **kwargs):
        self.calls.append(("goto", kwargs["timeout"]))
        return "ok"

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.calls.append(("wait_for_timeout", milliseconds))

    def wait_for_load_state(self, *args, **kwargs) -> None:
        self.calls.append(("wait_for_load_state", kwargs["timeout"]))

    def screenshot(self, *args, **kwargs) -> None:
        self.calls.append(("screenshot", kwargs["timeout"]))


def test_bounded_timeout_is_clamped_to_remaining_source_budget(monkeypatch) -> None:
    monkeypatch.setattr(authority.time, "time", lambda: 100.0)
    token = authority._ACTIVE_DEADLINE.set(131.5)
    try:
        assert authority.bounded_timeout_ms(5000) == 1500
    finally:
        authority._ACTIVE_DEADLINE.reset(token)


def test_expired_budget_raises_before_starting_another_browser_wait(monkeypatch) -> None:
    monkeypatch.setattr(authority.time, "time", lambda: 100.0)
    token = authority._ACTIVE_DEADLINE.set(129.0)
    try:
        with pytest.raises(
            authority.CollectionDeadlineExceeded,
            match="local_event_collection_deadline_exceeded",
        ):
            authority.bounded_timeout_ms(5000)
    finally:
        authority._ACTIVE_DEADLINE.reset(token)


def test_page_proxy_clamps_navigation_wait_and_screenshot(monkeypatch) -> None:
    monkeypatch.setattr(authority.time, "time", lambda: 100.0)
    page = FakePage()
    wrapped = authority._DeadlinePage(page)
    token = authority._ACTIVE_DEADLINE.set(131.5)
    try:
        assert wrapped.goto("https://example.test", timeout=5000) == "ok"
        wrapped.wait_for_timeout(5000)
        wrapped.wait_for_load_state("networkidle", timeout=5000)
        wrapped.screenshot(timeout=5000)
    finally:
        authority._ACTIVE_DEADLINE.reset(token)

    assert page.calls == [
        ("goto", 1500),
        ("wait_for_timeout", 1500),
        ("wait_for_load_state", 1500),
        ("screenshot", 1500),
    ]


def test_collect_source_propagates_and_resets_context_deadline(monkeypatch) -> None:
    observed: list[float | None] = []

    def base_collect(source, debug_dir, deadline):
        observed.append(authority.active_deadline())
        return [], {"ok": True}

    monkeypatch.setattr(authority, "_BASE_COLLECT_SOURCE", base_collect)

    assert authority.active_deadline() is None
    assert authority.collect_source({}, None, 1234.5) == ([], {"ok": True})
    assert observed == [1234.5]
    assert authority.active_deadline() is None


def test_http_bootstrap_installs_deadline_before_coverage_and_source_authorities() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    deadline = bootstrap.index("apply_deadline_authority()")
    coverage = bootstrap.index("apply_complete_collection()")
    provenance = bootstrap.index("apply_listing_provenance_authority()")

    assert deadline < coverage < provenance
