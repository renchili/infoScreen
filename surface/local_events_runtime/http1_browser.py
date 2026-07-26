from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Iterable

from . import browser as _browser

_APPLIED = False
_SNAP_WRAPPER_MARKERS = (
    b"/snap/bin/chromium",
    b"/usr/bin/snap",
    b"/bin/snap",
    b"snap run chromium",
    b"exec snap",
)


def _file_uses_snap(path: Path) -> bool:
    """Detect Ubuntu Chromium launchers that delegate to Snap."""

    try:
        if not path.is_file():
            return False
        with path.open("rb") as handle:
            prefix = handle.read(32_768).lower()
    except OSError:
        return False
    return any(marker in prefix for marker in _SNAP_WRAPPER_MARKERS)


def _is_snap_browser(value: object) -> bool:
    """Return whether a browser path is provided by Snap.

    Ubuntu exposes Snap Chromium through ordinary-looking paths such as
    ``/usr/bin/chromium-browser``. Reject the public path, resolved target, direct
    snap executable, and wrapper scripts that delegate to Snap instead of treating
    the resulting SIGTRAP browser death as a page failure.
    """

    text = str(value or "").strip()
    if not text:
        return False

    expanded = Path(text).expanduser()
    paths = {str(expanded)}
    resolved = expanded
    try:
        resolved = expanded.resolve(strict=False)
        paths.add(str(resolved))
    except (OSError, RuntimeError):
        pass

    if any(
        path in {"/usr/bin/snap", "/bin/snap"}
        or path == "/snap"
        or path.startswith("/snap/")
        or path == "/var/lib/snapd/snap"
        or path.startswith("/var/lib/snapd/snap/")
        for path in paths
    ):
        return True

    return _file_uses_snap(expanded) or (
        resolved != expanded and _file_uses_snap(resolved)
    )


def _select_browser_executable(candidates: Iterable[object]) -> str:
    """Return the first executable non-Snap browser candidate."""

    seen: set[str] = set()
    for value in candidates:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if _is_snap_browser(text):
            continue
        path = Path(text).expanduser()
        try:
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        except OSError:
            continue
    return ""


def _find_supported_browser_executable() -> str:
    """Find a Playwright-compatible system browser without selecting Snap Chromium."""

    env_path = os.environ.get("INFOSCREEN_CHROMIUM_PATH") or os.environ.get(
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE"
    )
    return _select_browser_executable(
        [
            env_path,
            shutil.which("google-chrome-stable"),
            shutil.which("google-chrome"),
            shutil.which("microsoft-edge-stable"),
            shutil.which("microsoft-edge"),
            shutil.which("brave-browser"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/microsoft-edge-stable",
            "/usr/bin/microsoft-edge",
            "/usr/bin/brave-browser",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
    )


def _bind_final_browser_runtime_to_review() -> None:
    """Make Studio use the final browser rules, not import-time snapshots.

    ``event_review`` imports browser constants with ``from .browser import ...``.
    Several authorities intentionally rewrite the browser JavaScript after that
    module has already been imported, so its local names otherwise remain stale.
    This binding is the single final handoff after every browser authority has run.
    """
    from . import event_review as review

    for name in (
        "CARD_JS",
        "CLICK_NEXT_PAGE_JS",
        "DETAIL_CARD_JS",
        "DOM_TIMEOUT_MS",
        "LOAD_MORE_ROUNDS",
        "MAX_LISTING_PAGES",
        "NAV_TIMEOUT_MS",
        "NEXT_WAIT_MS",
        "PREPARE_PAGE_JS",
        "launch_chromium",
        "merge_detail_payload",
    ):
        setattr(review, name, getattr(_browser, name))


def apply() -> None:
    """Install the shared Local Events browser and review-backend bootstrap.

    Collection starts in HTTP/1.1 mode directly. Snap Chromium and Ubuntu wrapper
    scripts that delegate to it are not selected because they terminate with SIGTRAP
    under the Surface user service. Listing navigation accepts a readable rendered
    document even when lifecycle events do not settle. Review detail pages are read
    through the existing bounded blocking reader, one admitted card at a time, so no
    unconsumed background tabs remain when the listing or BrowserContext is closed.
    All browser and event authorities are applied before their final values are bound
    into Review Studio.
    """
    global _APPLIED
    if _APPLIED:
        return

    def launch_chromium_http1(playwright: Any):
        from .resilient_navigation_authority import apply as apply_navigation

        apply_navigation()
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-http2",
        ]
        executable = _find_supported_browser_executable()
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
                "missing_compatible_chromium: Snap Chromium is unsupported for the "
                "InfoScreen Playwright service and no compatible browser could be "
                "launched. Install Google Chrome/Chromium as a normal executable or "
                "install Playwright Chromium, then optionally set "
                "INFOSCREEN_CHROMIUM_PATH to that non-Snap executable. "
                f"Original error: {exc}"
            ) from exc

    _browser.launch_chromium = launch_chromium_http1

    from .deadline_authority import apply as apply_deadline_authority
    apply_deadline_authority()

    from .complete_collection_authority import apply as apply_complete_collection
    apply_complete_collection()

    from .detail_date_authority import apply as apply_detail_date_authority
    apply_detail_date_authority()

    from .detail_payload_authority import apply as apply_detail_payload_authority
    apply_detail_payload_authority()

    from .detail_summary_authority import apply as apply_detail_summary_authority
    apply_detail_summary_authority()

    from .review_detail_navigation_authority import (
        apply as apply_review_detail_navigation_authority,
    )
    apply_review_detail_navigation_authority()

    from .dynamic_listing_authority import apply as apply_dynamic_listing_authority
    apply_dynamic_listing_authority()

    from .open_ended_date_authority import apply as apply_open_ended_date_authority
    apply_open_ended_date_authority()

    from .open_detail_fields_authority import apply as apply_open_detail_fields_authority
    apply_open_detail_fields_authority()

    from .gardens_field_authority import apply as apply_gardens_field_authority
    apply_gardens_field_authority()

    from .listing_provenance_authority import apply as apply_listing_provenance_authority
    apply_listing_provenance_authority()

    from .listing_membership_authority import apply as apply_listing_membership_authority
    apply_listing_membership_authority()

    from .mandai_listing_authority import apply as apply_mandai_listing_authority
    apply_mandai_listing_authority()

    from .structural_link_authority import apply as apply_structural_link_authority
    apply_structural_link_authority()

    from .listing_url_authority import apply as apply_listing_url_authority
    apply_listing_url_authority()

    # Apply this last over the composed event authority so explicit Where/Location
    # labels and public URL rewrites survive every source/membership wrapper.
    from .detail_authority import apply as apply_detail_authority
    apply_detail_authority()

    # event_review was imported before the final JavaScript rewrites above. Rebind
    # only after all browser and event authorities have their final values.
    _bind_final_browser_runtime_to_review()

    from .review_effective_fields_authority import (
        apply as apply_review_effective_fields_authority,
    )
    apply_review_effective_fields_authority()

    from .event_review_diagnostics import apply as apply_event_review_diagnostics
    apply_event_review_diagnostics()

    from .review_summary_authority import apply as apply_review_summary_authority
    apply_review_summary_authority()

    from .review_publish_authority import apply as apply_review_publish_authority
    apply_review_publish_authority()
    _APPLIED = True


__all__ = [
    "apply",
    "_find_supported_browser_executable",
    "_is_snap_browser",
    "_select_browser_executable",
]
