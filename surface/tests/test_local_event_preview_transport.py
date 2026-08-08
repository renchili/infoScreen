from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser as browser_runtime  # noqa: E402
from local_events_runtime import preview_transport_authority as transport  # noqa: E402


class PreviewStore:
    def __init__(self, root, url: str) -> None:
        self.root = root
        self._url = url

    def load(self):
        return SimpleNamespace(
            listing_pages=[
                SimpleNamespace(decision="confirmed", url=self._url),
            ]
        )


def test_preview_browser_keeps_http2_and_captures_netlog(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}
    navigation_calls: list[bool] = []

    class Browser:
        version = "149.0.0.0"

    class Chromium:
        executable_path = "/home/rody/.cache/ms-playwright/chromium/chrome"

        def launch(self, **kwargs):
            observed.update(kwargs)
            return Browser()

    class Playwright:
        chromium = Chromium()

    netlog = tmp_path / "preview-netlog.json"
    monkeypatch.delenv("INFOSCREEN_CHROMIUM_PATH", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)
    monkeypatch.setattr(transport, "_new_netlog_path", lambda executable: netlog)
    monkeypatch.setattr(transport._navigation, "apply", lambda: navigation_calls.append(True))
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", True)

    result = transport._launch_preview_chromium(Playwright())

    assert isinstance(result, Browser)
    assert navigation_calls == [True]
    assert observed["headless"] is True
    assert "executable_path" not in observed
    assert "--disable-http2" not in observed["args"]
    assert "--no-sandbox" not in observed["args"]
    assert "--disable-dev-shm-usage" not in observed["args"]
    assert "--disable-gpu" not in observed["args"]
    assert "--start-minimized" not in observed["args"]
    assert f"--log-net-log={netlog}" in observed["args"]
    assert "--net-log-capture-mode=Default" in observed["args"]
    assert transport._LAST_PREVIEW_DIAGNOSTIC == {
        "browser_executable": Chromium.executable_path,
        "browser_source": "playwright-managed",
        "browser_version": "149.0.0.0",
        "browser_mode": "headless",
        "netlog": str(netlog),
    }


def test_mbs_preview_launches_playwright_managed_chromium_headed(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    class Browser:
        version = "150.0.7871.128"

    class Chromium:
        executable_path = "/home/rody/.cache/ms-playwright/chromium/chrome"

        def launch(self, **kwargs):
            observed.update(kwargs)
            return Browser()

    class Playwright:
        chromium = Chromium()

    netlog = tmp_path / "preview-netlog.json"
    monkeypatch.delenv("INFOSCREEN_CHROMIUM_PATH", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)
    monkeypatch.setattr(transport, "_new_netlog_path", lambda executable: netlog)
    monkeypatch.setattr(transport._navigation, "apply", lambda: None)
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", False)

    result = transport._launch_preview_chromium(Playwright())

    assert isinstance(result, Browser)
    assert observed["headless"] is False
    assert "executable_path" not in observed
    assert "--start-minimized" in observed["args"]
    assert "--disable-http2" not in observed["args"]
    assert transport._LAST_PREVIEW_DIAGNOSTIC["browser_source"] == "playwright-managed"
    assert transport._LAST_PREVIEW_DIAGNOSTIC["browser_mode"] == "headed"


def test_explicit_browser_path_is_the_only_executable_override(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    class Browser:
        version = "150.0.0.0"

    class Chromium:
        executable_path = "/managed/chromium"

        def launch(self, **kwargs):
            observed.update(kwargs)
            return Browser()

    class Playwright:
        chromium = Chromium()

    explicit = tmp_path / "configured-chromium"
    explicit.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("INFOSCREEN_CHROMIUM_PATH", str(explicit))
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)
    monkeypatch.setattr(
        transport,
        "_new_netlog_path",
        lambda executable: tmp_path / "netlog.json",
    )
    monkeypatch.setattr(transport._navigation, "apply", lambda: None)
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", True)

    transport._launch_preview_chromium(Playwright())

    assert observed["executable_path"] == str(explicit)
    assert transport._LAST_PREVIEW_DIAGNOSTIC["browser_source"] == "configured"
    assert transport._LAST_PREVIEW_DIAGNOSTIC["browser_executable"] == str(explicit)


def test_missing_explicit_browser_fails_before_launch(monkeypatch, tmp_path) -> None:
    launch_calls: list[dict[str, object]] = []

    class Chromium:
        executable_path = "/managed/chromium"

        def launch(self, **kwargs):
            launch_calls.append(kwargs)
            raise AssertionError("launch must not run for a missing configured file")

    class Playwright:
        chromium = Chromium()

    missing = tmp_path / "missing-chromium"
    monkeypatch.setenv("INFOSCREEN_CHROMIUM_PATH", str(missing))
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)
    monkeypatch.setattr(transport._navigation, "apply", lambda: None)
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", True)

    with pytest.raises(browser_runtime.MissingPlaywright) as raised:
        transport._launch_preview_chromium(Playwright())

    assert "preview_chromium_selection_failed" in str(raised.value)
    assert "configured_chromium_not_found" in str(raised.value)
    assert launch_calls == []
    assert transport._LAST_PREVIEW_DIAGNOSTIC == {
        "browser_executable": str(missing),
        "browser_source": "configured",
        "browser_version": "",
        "browser_mode": "headless",
        "netlog": "",
    }


def test_only_mbs_listing_requires_headed_preview(tmp_path) -> None:
    mbs = PreviewStore(
        tmp_path / "infoscreen-event-preview-mbs",
        "https://www.marinabaysands.com/museum/whats-on.html",
    )
    other = PreviewStore(
        tmp_path / "infoscreen-event-preview-other",
        "https://www.science.edu.sg/whats-on",
    )

    assert transport._requires_headed_preview(mbs) is True
    assert transport._requires_headed_preview(other) is False


def test_mbs_preview_uses_headed_mode_and_restores_launcher(monkeypatch, tmp_path) -> None:
    original_launch = object()
    modes: list[bool] = []
    store = PreviewStore(
        tmp_path / "infoscreen-event-preview-mbs",
        "https://www.marinabaysands.com/museum/whats-on.html",
    )

    def base_collect(actual_store):
        assert actual_store is store
        modes.append(transport._PREVIEW_HEADLESS)
        assert browser_runtime.launch_chromium is transport._launch_preview_chromium
        return "preview-state"

    monkeypatch.setattr(transport, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(transport, "_graphical_session_available", lambda: True)
    monkeypatch.setattr(browser_runtime, "launch_chromium", original_launch)
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", True)

    result = transport.collect_event_candidates(store)

    assert result == "preview-state"
    assert modes == [False]
    assert browser_runtime.launch_chromium is original_launch
    assert transport._PREVIEW_HEADLESS is True


def test_mbs_preview_fails_clearly_without_graphical_session(monkeypatch, tmp_path) -> None:
    store = PreviewStore(
        tmp_path / "infoscreen-event-preview-mbs",
        "https://www.marinabaysands.com/museum/whats-on.html",
    )
    base_calls: list[object] = []
    monkeypatch.setattr(transport, "_BASE_COLLECT", lambda actual: base_calls.append(actual))
    monkeypatch.setattr(transport, "_graphical_session_available", lambda: False)

    with pytest.raises(RuntimeError) as raised:
        transport.collect_event_candidates(store)

    assert "graphical session" in str(raised.value)
    assert "DISPLAY" in str(raised.value)
    assert base_calls == []


def test_snap_chromium_netlog_uses_host_visible_user_common(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INFOSCREEN_PREVIEW_NETLOG_DIR", raising=False)
    monkeypatch.setattr(transport.Path, "home", lambda: tmp_path)

    path = transport._new_netlog_path("/snap/bin/chromium")

    assert path.parent == tmp_path / "snap" / "chromium" / "common" / "infoscreen-netlog"
    assert path.name.startswith("infoscreen-preview-netlog-")
    assert path.suffix == ".json"
    assert path.parent.is_dir()


def test_non_snap_chromium_netlog_keeps_system_tmp(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INFOSCREEN_PREVIEW_NETLOG_DIR", raising=False)
    monkeypatch.setattr(transport.tempfile, "gettempdir", lambda: str(tmp_path))

    path = transport._new_netlog_path("/usr/bin/google-chrome")

    assert path.parent == tmp_path


def test_preview_transport_restores_formal_browser_launcher(monkeypatch, tmp_path) -> None:
    original_launch = object()
    preview_launch_seen: list[object] = []

    class Store:
        root = tmp_path / "infoscreen-event-preview-test"

        def load(self):
            return SimpleNamespace(listing_pages=[])

    def base_collect(store):
        preview_launch_seen.append(browser_runtime.launch_chromium)
        return "preview-state"

    monkeypatch.setattr(transport, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(browser_runtime, "launch_chromium", original_launch)

    result = transport.collect_event_candidates(Store())

    assert result == "preview-state"
    assert preview_launch_seen == [transport._launch_preview_chromium]
    assert browser_runtime.launch_chromium is original_launch


def test_netlog_summary_keeps_http2_error_evidence(monkeypatch, tmp_path) -> None:
    netlog = tmp_path / "preview.json"
    netlog.write_text(
        json.dumps(
            {
                "constants": {
                    "logEventTypes": {
                        "HTTP2_SESSION": 7,
                        "URL_REQUEST_START_JOB": 9,
                    }
                },
                "events": [
                    {
                        "time": "10",
                        "type": 7,
                        "phase": 0,
                        "source": {"id": 4, "type": 1},
                        "params": {
                            "description": "Received RST_STREAM",
                            "stream_id": 1,
                            "net_error": -337,
                        },
                    },
                    {
                        "time": "11",
                        "type": 9,
                        "phase": 0,
                        "source": {"id": 5, "type": 1},
                        "params": {"url": "https://www.marinabaysands.com/"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = transport._write_netlog_summary(
        {
            "browser_executable": "/usr/bin/chromium",
            "browser_source": "configured",
            "browser_version": "149.0.0.0",
            "browser_mode": "headless",
            "netlog": str(netlog),
        }
    )

    payload = json.loads((tmp_path / "preview.summary.json").read_text(encoding="utf-8"))
    assert summary == str(tmp_path / "preview.summary.json")
    assert payload["browser_executable"] == "/usr/bin/chromium"
    assert payload["browser_source"] == "configured"
    assert payload["browser_mode"] == "headless"
    assert payload["events"][0]["type"] == "HTTP2_SESSION"
    assert payload["events"][0]["params"]["net_error"] == -337


def test_preview_failure_reports_browser_mode_and_netlog(monkeypatch, tmp_path) -> None:
    original_launch = object()
    netlog = tmp_path / "preview.json"
    netlog.write_text(json.dumps({"constants": {}, "events": []}), encoding="utf-8")

    class Store:
        root = tmp_path / "infoscreen-event-preview-test"

        def load(self):
            return SimpleNamespace(listing_pages=[])

    def base_collect(store):
        transport._LAST_PREVIEW_DIAGNOSTIC = {
            "browser_executable": "/usr/bin/chromium",
            "browser_source": "configured",
            "browser_version": "149.0.0.0",
            "browser_mode": "headless",
            "netlog": str(netlog),
        }
        raise RuntimeError("ERR_HTTP2_PROTOCOL_ERROR")

    monkeypatch.setattr(transport, "_BASE_COLLECT", base_collect)
    monkeypatch.setattr(browser_runtime, "launch_chromium", original_launch)

    with pytest.raises(RuntimeError) as raised:
        transport.collect_event_candidates(Store())

    message = str(raised.value)
    assert "ERR_HTTP2_PROTOCOL_ERROR" in message
    assert "preview_browser=/usr/bin/chromium" in message
    assert "preview_browser_source=configured" in message
    assert "preview_browser_version=149.0.0.0" in message
    assert "preview_browser_mode=headless" in message
    assert f"preview_netlog={netlog}" in message
    assert "preview_netlog_summary=" in message
    assert browser_runtime.launch_chromium is original_launch
