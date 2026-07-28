from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser as browser_runtime  # noqa: E402
from local_events_runtime import preview_transport_authority as transport  # noqa: E402


def test_preview_browser_keeps_http2_and_installs_resilient_navigation(monkeypatch) -> None:
    observed: dict[str, object] = {}
    navigation_calls: list[bool] = []

    class Chromium:
        def launch(self, **kwargs):
            observed.update(kwargs)
            return "preview-browser"

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(
        browser_runtime,
        "find_browser_executable",
        lambda: "/usr/bin/chromium",
    )
    monkeypatch.setattr(
        transport._navigation,
        "apply",
        lambda: navigation_calls.append(True),
    )

    result = transport._launch_preview_chromium(Playwright())

    assert result == "preview-browser"
    assert navigation_calls == [True]
    assert observed["headless"] is True
    assert observed["executable_path"] == "/usr/bin/chromium"
    assert "--disable-http2" not in observed["args"]


def test_preview_transport_restores_formal_browser_launcher(monkeypatch, tmp_path) -> None:
    original_launch = object()
    preview_launch_seen: list[object] = []

    class Store:
        root = tmp_path / "infoscreen-event-preview-test"

    def base_collect(store):
        preview_launch_seen.append(browser_runtime.launch_chromium)
        return "preview-state"

    monkeypatch.setattr(transport, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(browser_runtime, "launch_chromium", original_launch)

    result = transport.collect_event_candidates(Store())

    assert result == "preview-state"
    assert preview_launch_seen == [transport._launch_preview_chromium]
    assert browser_runtime.launch_chromium is original_launch
