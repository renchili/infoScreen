from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_browser_session_authority as authority  # noqa: E402


class StoredState:
    def __init__(self) -> None:
        self.events = []
        self.event_collection = {
            "preview_detail_context_count": 1,
            "preview_detail_isolated_browser_count": 2,
        }


class Store:
    def __init__(self) -> None:
        self.saved = []

    def save(self, state):
        self.saved.append(state)
        return state


def test_preview_launcher_forces_http1_for_headed_snap_chromium(
    monkeypatch,
    tmp_path,
) -> None:
    launches = []

    class Browser:
        version = "150.0"

    class Chromium:
        def launch(self, **kwargs):
            launches.append(kwargs)
            return Browser()

    monkeypatch.setattr(authority._transport._navigation, "apply", lambda: None)
    monkeypatch.setattr(
        authority._browser,
        "find_browser_executable",
        lambda: "/snap/bin/chromium",
    )
    monkeypatch.setattr(
        authority._transport,
        "_new_netlog_path",
        lambda executable: Path(tmp_path) / "preview-netlog.json",
    )
    monkeypatch.setattr(authority._transport, "_PREVIEW_HEADLESS", False)

    browser = authority.launch_preview_chromium(
        SimpleNamespace(chromium=Chromium())
    )

    assert browser.version == "150.0"
    assert len(launches) == 1
    assert launches[0]["headless"] is False
    assert launches[0]["executable_path"] == "/snap/bin/chromium"
    assert "--disable-http2" in launches[0]["args"]
    assert "--start-minimized" in launches[0]["args"]


def test_preview_listing_and_details_borrow_one_request_local_browser(
    monkeypatch,
) -> None:
    owners = [object(), object(), object()]
    entered = []
    exited = []
    next_owner = 0
    browser_launches = []
    fallback_launches = []
    borrowed_browsers = []
    final_detail_guards = []

    class PlaywrightContext:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            entered.append(self.owner)
            return self.owner

        def __exit__(self, exc_type, exc, traceback):
            exited.append(self.owner)
            return False

    sync_api = ModuleType("playwright.sync_api")

    def sync_playwright():
        nonlocal next_owner
        owner = owners[next_owner]
        next_owner += 1
        return PlaywrightContext(owner)

    sync_api.sync_playwright = sync_playwright
    playwright = ModuleType("playwright")
    playwright.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    class Browser:
        def __init__(self):
            self.close_count = 0

        def close(self):
            self.close_count += 1

    browser = Browser()

    def launch(owner_playwright):
        browser_launches.append(owner_playwright)
        return browser

    def fallback(playwright):
        fallback_launches.append(playwright)
        raise AssertionError("Preview must borrow the request browser")

    monkeypatch.setattr(authority, "launch_preview_chromium", launch)
    monkeypatch.setattr(authority, "_BASE_BROWSER_LAUNCH", fallback)
    monkeypatch.setattr(authority._browser, "launch_chromium", authority.launch_or_borrow)
    monkeypatch.setattr(authority._transport, "_preview_store", lambda store: True)
    monkeypatch.setattr(
        authority._transport,
        "_requires_headed_preview",
        lambda store: False,
    )

    def base_collect(store):
        # The direct listing collector and detail enrichment each create a temporary
        # Playwright manager. Both browser launches must resolve to the request lease.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as listing_playwright:
            listing_browser = authority._browser.launch_chromium(listing_playwright)
            borrowed_browsers.append(listing_browser)
            listing_browser.close()

        with sync_playwright() as detail_playwright:
            detail_browser = authority._browser.launch_chromium(detail_playwright)
            borrowed_browsers.append(detail_browser)
            detail_browser.close()

        return StoredState()

    def final_detail_guard(store, state):
        session = authority._CURRENT_SESSION.get()
        final_detail_guards.append(session)
        assert session is not None
        assert session.browser is browser
        assert browser.close_count == 0
        return state

    monkeypatch.setattr(authority._transport, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(
        authority,
        "_enrich_remaining_preview_details",
        final_detail_guard,
    )
    store = Store()

    state = authority.collect_event_candidates(store)

    assert entered == owners
    assert exited == [owners[1], owners[2], owners[0]]
    assert browser_launches == [owners[0]]
    assert fallback_launches == []
    assert len(borrowed_browsers) == 2
    assert all(isinstance(item, authority.PreviewBrowserLease) for item in borrowed_browsers)
    assert borrowed_browsers[0] is borrowed_browsers[1]
    assert len(final_detail_guards) == 1
    assert browser.close_count == 1
    assert authority._CURRENT_SESSION.get() is None
    assert store.saved == [state]
    assert state.event_collection["preview_browser_process_count"] == 1
    assert state.event_collection["preview_browser_reuse"] == "listing_and_details"
    assert state.event_collection["preview_detail_transport"] == (
        "single_http1_browser_process"
    )
    assert state.event_collection["preview_detail_context_count"] == 1
    assert "preview_detail_isolated_browser_count" not in state.event_collection


def test_final_detail_fallback_requires_active_request_session(monkeypatch) -> None:
    candidate = SimpleNamespace(
        detail_error="preview_listing_evidence_only_missing_when"
    )
    state = SimpleNamespace(events=[candidate], event_collection={})

    from local_events_runtime import preview_detail_enrichment_authority as enrichment

    monkeypatch.setattr(enrichment, "_needs_detail", lambda item: True)

    with pytest.raises(RuntimeError, match="active request-local browser session"):
        authority._enrich_remaining_preview_details(Store(), state)


def test_final_detail_fallback_uses_active_request_session(monkeypatch) -> None:
    candidate = SimpleNamespace(
        detail_error="preview_listing_evidence_only_missing_when"
    )
    state = SimpleNamespace(events=[candidate], event_collection={})
    expected = SimpleNamespace(events=[], event_collection={})
    browser = object()
    session = authority.PreviewBrowserSession(
        browser=browser,
        lease=authority.PreviewBrowserLease(browser),
    )
    calls = []

    from local_events_runtime import preview_detail_enrichment_authority as enrichment

    monkeypatch.setattr(enrichment, "_needs_detail", lambda item: True)

    def enrich(store, actual):
        calls.append((store, actual, authority._CURRENT_SESSION.get()))
        return expected

    monkeypatch.setattr(enrichment, "enrich_preview_state", enrich)
    store = Store()
    token = authority._CURRENT_SESSION.set(session)
    try:
        result = authority._enrich_remaining_preview_details(store, state)
    finally:
        authority._CURRENT_SESSION.reset(token)

    assert result is expected
    assert calls == [(store, state, session)]


def test_non_preview_launch_uses_the_original_browser_launcher(monkeypatch) -> None:
    calls = []
    expected = object()

    monkeypatch.setattr(authority, "_BASE_BROWSER_LAUNCH", lambda p: calls.append(p) or expected)

    playwright = object()
    assert authority.launch_or_borrow(playwright) is expected
    assert calls == [playwright]


def test_reapply_restores_the_global_lease_launcher(monkeypatch) -> None:
    fallback = lambda playwright: playwright
    replacement = object()

    monkeypatch.setattr(authority, "_APPLIED", True)
    monkeypatch.setattr(authority, "_BASE_BROWSER_LAUNCH", fallback)
    monkeypatch.setattr(authority._browser, "launch_chromium", replacement)

    authority.apply()

    assert authority._BASE_BROWSER_LAUNCH is fallback
    assert authority._browser.launch_chromium is authority.launch_or_borrow
    assert authority._transport._launch_preview_chromium is (
        authority.launch_preview_chromium
    )
    assert authority._transport.collect_event_candidates is (
        authority.collect_event_candidates
    )


def test_transport_hook_runs_after_existing_preview_composition(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(authority, "_HOOKED", False)
    monkeypatch.setattr(authority, "_BASE_TRANSPORT_APPLY", None)
    monkeypatch.setattr(authority._transport, "_APPLIED", False)

    def base_apply():
        calls.append("base")
        authority._transport._APPLIED = True

    monkeypatch.setattr(authority._transport, "apply", base_apply)
    monkeypatch.setattr(authority, "apply", lambda: calls.append("single-session"))

    authority.install_transport_apply_hook()
    authority._transport.apply()

    assert calls == ["base", "single-session"]
