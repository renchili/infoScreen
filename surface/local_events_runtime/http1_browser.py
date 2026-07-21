from __future__ import annotations

from typing import Any

from . import browser as _browser

_APPLIED = False


def apply() -> None:
    """Force every patched Local Events Chromium launch to disable HTTP/2.

    The Surface has observed Chromium navigation failures with
    ERR_HTTP2_PROTOCOL_ERROR on official Event sites. Collection should start in
    HTTP/1.1 mode directly; it must not perform a first HTTP/2 attempt or retry by
    switching browser instances.
    """

    global _APPLIED
    if _APPLIED:
        return

    original_find = _browser.find_browser_executable

    def launch_chromium_http1(playwright: Any):
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-http2",
        ]
        executable = original_find()
        if executable:
            return playwright.chromium.launch(
                headless=True,
                executable_path=executable,
                args=args,
            )
        try:
            return playwright.chromium.launch(headless=True, args=args)
        except Exception as exc:
            raise _browser.MissingPlaywright(
                "missing_system_chromium: Playwright bundled Chromium is unavailable "
                "on this distro. Install a system browser and set "
                "INFOSCREEN_CHROMIUM_PATH if needed. Examples: sudo apt install "
                "chromium; or install Google Chrome and export "
                "INFOSCREEN_CHROMIUM_PATH=/usr/bin/google-chrome. "
                f"Original error: {exc}"
            ) from exc

    _browser.launch_chromium = launch_chromium_http1
    _APPLIED = True


__all__ = ["apply"]
