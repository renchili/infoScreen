from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import preview_transport_authority as _transport

_APPLIED = False
_BASE_GRAPHICAL_SESSION_AVAILABLE = None
_BASE_LAUNCH_PREVIEW_CHROMIUM = None
_SESSION_ENV_NAMES = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_RUNTIME_DIR",
)
_BROWSER_PROCESS_MARKERS = ("chromium", "chrome")


def _usable_environment(values: dict[str, str]) -> bool:
    return bool(values.get("DISPLAY") or values.get("WAYLAND_DISPLAY"))


def _current_environment() -> dict[str, str]:
    values = {
        name: str(os.environ.get(name) or "").strip()
        for name in _SESSION_ENV_NAMES
    }
    return {name: value for name, value in values.items() if value}


def _process_environment(process_dir: Path) -> tuple[int, dict[str, str]] | None:
    try:
        if process_dir.stat().st_uid != os.getuid():
            return None
        command = process_dir.joinpath("cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", "replace"
        )
        lowered = command.casefold()
        if not any(marker in lowered for marker in _BROWSER_PROCESS_MARKERS):
            return None
        raw = process_dir.joinpath("environ").read_bytes().split(b"\0")
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None

    values: dict[str, str] = {}
    for item in raw:
        if b"=" not in item:
            continue
        name, value = item.split(b"=", 1)
        decoded_name = name.decode("utf-8", "replace")
        if decoded_name not in _SESSION_ENV_NAMES:
            continue
        decoded_value = value.decode("utf-8", "replace").strip()
        if decoded_value:
            values[decoded_name] = decoded_value
    if not _usable_environment(values):
        return None

    score = 0
    if "--kiosk" in lowered:
        score += 100
    if values.get("DISPLAY"):
        score += 20
    if values.get("WAYLAND_DISPLAY"):
        score += 10
    if values.get("XAUTHORITY"):
        score += 5
    return score, values


def _active_browser_environment(proc_root: Path = Path("/proc")) -> dict[str, str]:
    candidates: list[tuple[int, int, dict[str, str]]] = []
    try:
        process_dirs = list(proc_root.iterdir())
    except OSError:
        return {}

    for process_dir in process_dirs:
        if not process_dir.name.isdigit():
            continue
        result = _process_environment(process_dir)
        if result is None:
            continue
        score, values = result
        candidates.append((score, int(process_dir.name), values))

    if not candidates:
        return {}
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def graphical_session_environment() -> dict[str, str]:
    """Find the graphical environment owned by the active Surface browser session."""

    current = _current_environment()
    if _usable_environment(current):
        return current
    return _active_browser_environment()


@contextmanager
def borrow_graphical_session() -> Iterator[dict[str, str]]:
    """Temporarily expose the active kiosk session to a headed Preview launch."""

    values = graphical_session_environment()
    if not _usable_environment(values):
        raise RuntimeError(
            "MBS preview requires an active Surface graphical session, but no DISPLAY "
            "or WAYLAND_DISPLAY could be found in the HTTP process or any same-user "
            "Chromium kiosk process"
        )

    previous = {name: os.environ.get(name) for name in values}
    try:
        os.environ.update(values)
        yield values
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _graphical_session_available() -> bool:
    return _usable_environment(graphical_session_environment())


def _launch_preview_chromium(playwright: Any):
    if _transport._PREVIEW_HEADLESS or _usable_environment(_current_environment()):
        return _BASE_LAUNCH_PREVIEW_CHROMIUM(playwright)
    with borrow_graphical_session():
        return _BASE_LAUNCH_PREVIEW_CHROMIUM(playwright)


def apply() -> None:
    """Make headed Preview work from the unattended HTTP service."""

    global _APPLIED
    global _BASE_GRAPHICAL_SESSION_AVAILABLE
    global _BASE_LAUNCH_PREVIEW_CHROMIUM

    if _APPLIED:
        _transport._graphical_session_available = _graphical_session_available
        _transport._launch_preview_chromium = _launch_preview_chromium
        return

    _BASE_GRAPHICAL_SESSION_AVAILABLE = _transport._graphical_session_available
    _BASE_LAUNCH_PREVIEW_CHROMIUM = _transport._launch_preview_chromium
    _transport._graphical_session_available = _graphical_session_available
    _transport._launch_preview_chromium = _launch_preview_chromium
    _APPLIED = True


__all__ = [
    "apply",
    "borrow_graphical_session",
    "graphical_session_environment",
]
