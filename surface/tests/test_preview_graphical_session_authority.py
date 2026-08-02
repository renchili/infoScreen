from __future__ import annotations

import os
import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_graphical_session_authority as graphical  # noqa: E402
from local_events_runtime import preview_transport_authority as transport  # noqa: E402


def test_graphical_environment_is_borrowed_from_same_user_kiosk(monkeypatch, tmp_path) -> None:
    proc = tmp_path / "proc"
    normal = proc / "101"
    kiosk = proc / "202"
    normal.mkdir(parents=True)
    kiosk.mkdir(parents=True)
    normal.joinpath("cmdline").write_bytes(b"/snap/bin/chromium\0https://example.com\0")
    normal.joinpath("environ").write_bytes(b"DISPLAY=:1\0XAUTHORITY=/tmp/normal-auth\0")
    kiosk.joinpath("cmdline").write_bytes(
        b"/snap/bin/chromium\0--kiosk\0http://127.0.0.1:8765/\0"
    )
    kiosk.joinpath("environ").write_bytes(
        b"DISPLAY=:0\0WAYLAND_DISPLAY=wayland-0\0"
        b"XAUTHORITY=/run/user/1000/gdm/Xauthority\0"
        b"XDG_RUNTIME_DIR=/run/user/1000\0"
    )

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(graphical.os, "getuid", lambda: os.stat(kiosk).st_uid)

    values = graphical._active_browser_environment(proc)

    assert values["DISPLAY"] == ":0"
    assert values["WAYLAND_DISPLAY"] == "wayland-0"
    assert values["XAUTHORITY"] == "/run/user/1000/gdm/Xauthority"


def test_headed_preview_temporarily_uses_borrowed_environment(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def launch(playwright):
        observed["display"] = os.environ.get("DISPLAY", "")
        observed["xauthority"] = os.environ.get("XAUTHORITY", "")
        return "browser"

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", False)
    monkeypatch.setattr(graphical, "_BASE_LAUNCH_PREVIEW_CHROMIUM", launch)
    monkeypatch.setattr(
        graphical,
        "graphical_session_environment",
        lambda: {"DISPLAY": ":0", "XAUTHORITY": "/run/user/1000/gdm/Xauthority"},
    )

    assert graphical._launch_preview_chromium(object()) == "browser"
    assert observed == {
        "display": ":0",
        "xauthority": "/run/user/1000/gdm/Xauthority",
    }
    assert "DISPLAY" not in os.environ
    assert "XAUTHORITY" not in os.environ


def test_headless_preview_does_not_require_graphical_environment(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(transport, "_PREVIEW_HEADLESS", True)
    monkeypatch.setattr(
        graphical,
        "_BASE_LAUNCH_PREVIEW_CHROMIUM",
        lambda playwright: calls.append(playwright) or "browser",
    )
    monkeypatch.setattr(
        graphical,
        "graphical_session_environment",
        lambda: (_ for _ in ()).throw(AssertionError("must not inspect session")),
    )

    token = object()
    assert graphical._launch_preview_chromium(token) == "browser"
    assert calls == [token]


def test_review_bootstrap_installs_graphical_session_authority() -> None:
    source = (SURFACE / "local_events_runtime" / "review_summary_authority.py").read_text(
        encoding="utf-8"
    )

    assert "apply_preview_graphical_session_authority" in source
    assert "apply_preview_graphical_session_authority()" in source
