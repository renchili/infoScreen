from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_browser_session_authority as authority  # noqa: E402


class StoredState:
    def __init__(self) -> None:
        self.event_collection = {
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


def test_preview_listing_and_details_borrow_one_playwright_and_browser(
    monkeypatch,
) -> None:
    owner = object()
    owner_enters = []
    owner_exits = []
    borrowed_owners = []
    browser_launches = []

    class OwnerContext:
        def __enter__(self):
            owner_enters.append(owner)
            return owner

        def __exit__(self, exc_type, exc, traceback):
            owner_exits.append(owner)
            return False

    sync_api = ModuleType("playwright.sync_api")

    def original_sync_playwright():
        return OwnerContext()

    sync_api.sync_playwright = original_sync_playwright
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

    monkeypatch.setattr(authority, "launch_preview_chromium", launch)
    monkeypatch.setattr(authority._transport, "_preview_store", lambda store: True)
    monkeypatch.setattr(
        authority._transport,
        "_requires_headed_preview",
        lambda store: False,
    )

    def base_collect(store):
        # Simulate the direct listing collector and detail enrichment entering their
        # own sync_playwright() blocks and both attempting to close the browser.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as listing_playwright:
            borrowed_owners.append(listing_playwright)
            listing_browser = authority._browser.launch_chromium(listing_playwright)
            listing_browser.close()

        with sync_playwright() as detail_playwright:
            borrowed_owners.append(detail_playwright)
            detail_browser = authority._browser.launch_chromium(detail_playwright)
            detail_browser.close()

        return StoredState()

    monkeypatch.setattr(authority._transport, "_BASE_COLLECT", base_collect)
    original_browser_launch = authority._browser.launch_chromium
    store = Store()

    state = authority.collect_event_candidates(store)

    assert owner_enters == [owner]
    assert owner_exits == [owner]
    assert borrowed_owners == [owner, owner]
    assert browser_launches == [owner]
    assert browser.close_count == 1
    assert authority._browser.launch_chromium is original_browser_launch
    assert sync_api.sync_playwright is original_sync_playwright
    assert store.saved == [state]
    assert state.event_collection["preview_browser_process_count"] == 1
    assert state.event_collection["preview_browser_reuse"] == "listing_and_details"
    assert state.event_collection["preview_detail_transport"] == (
        "single_http1_browser_process"
    )
    assert state.event_collection["preview_detail_isolated_context_count"] == 2
    assert "preview_detail_isolated_browser_count" not in state.event_collection


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
