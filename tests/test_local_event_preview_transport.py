from __future__ import annotations

import json
import sys

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser as browser_runtime  # noqa: E402
from local_events_runtime import preview_transport_authority as transport  # noqa: E402


def test_preview_browser_keeps_http2_and_captures_netlog(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}
    navigation_calls: list[bool] = []

    class Browser:
        version = "149.0.0.0"

    class Chromium:
        def launch(self, **kwargs):
            observed.update(kwargs)
            return Browser()

    class Playwright:
        chromium = Chromium()

    netlog = tmp_path / "preview-netlog.json"
    monkeypatch.setattr(
        browser_runtime,
        "find_browser_executable",
        lambda: "/usr/bin/chromium",
    )
    monkeypatch.setattr(transport, "_new_netlog_path", lambda: netlog)
    monkeypatch.setattr(
        transport._navigation,
        "apply",
        lambda: navigation_calls.append(True),
    )

    result = transport._launch_preview_chromium(Playwright())

    assert isinstance(result, Browser)
    assert navigation_calls == [True]
    assert observed["headless"] is True
    assert observed["executable_path"] == "/usr/bin/chromium"
    assert "--disable-http2" not in observed["args"]
    assert f"--log-net-log={netlog}" in observed["args"]
    assert "--net-log-capture-mode=Default" in observed["args"]
    assert transport._LAST_PREVIEW_DIAGNOSTIC == {
        "browser_executable": "/usr/bin/chromium",
        "browser_version": "149.0.0.0",
        "netlog": str(netlog),
    }


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
            "browser_version": "149.0.0.0",
            "netlog": str(netlog),
        }
    )

    payload = json.loads((tmp_path / "preview.summary.json").read_text(encoding="utf-8"))
    assert summary == str(tmp_path / "preview.summary.json")
    assert payload["browser_executable"] == "/usr/bin/chromium"
    assert payload["events"][0]["type"] == "HTTP2_SESSION"
    assert payload["events"][0]["params"]["net_error"] == -337


def test_preview_failure_reports_browser_and_netlog(monkeypatch, tmp_path) -> None:
    original_launch = object()
    netlog = tmp_path / "preview.json"
    netlog.write_text(json.dumps({"constants": {}, "events": []}), encoding="utf-8")

    class Store:
        root = tmp_path / "infoscreen-event-preview-test"

    def base_collect(store):
        transport._LAST_PREVIEW_DIAGNOSTIC = {
            "browser_executable": "/usr/bin/chromium",
            "browser_version": "149.0.0.0",
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
    assert "preview_browser_version=149.0.0.0" in message
    assert f"preview_netlog={netlog}" in message
    assert "preview_netlog_summary=" in message
    assert browser_runtime.launch_chromium is original_launch
