from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .browser import find_browser_executable
from .studio_capture import DOM_EVIDENCE_JS, write_snapshot
from .studio_evaluate import _write_test_run
from .studio_live_edit import save_live_selection
from .studio_live_overlay import OVERLAY_JS
from .studio_live_runtime import host_allowed
from .studio_live_validation import validate_current_listing
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRuleStore,
    canonical_listing_url,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(source_id: str, listing_url: str) -> str:
    digest = hashlib.sha256(
        canonical_listing_url(listing_url).encode("utf-8")
    ).hexdigest()[:12]
    return f"{source_id}-{digest}"


def _live_dir(root: Path) -> Path:
    path = root / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(root: Path, source_id: str, listing_url: str) -> Path:
    return _live_dir(root) / f"{_key(source_id, listing_url)}.json"


def _read_state(
    root: Path,
    source_id: str,
    listing_url: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            _state_path(root, source_id, listing_url).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(
    root: Path,
    source_id: str,
    listing_url: str,
    **changes: Any,
) -> dict[str, Any]:
    path = _state_path(root, source_id, listing_url)
    payload = {
        "source_id": source_id,
        "listing_url": canonical_listing_url(listing_url),
        **_read_state(root, source_id, listing_url),
        **changes,
        "updated_at": _now().isoformat(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return payload


def _alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_live_session(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> dict[str, Any]:
    """Start one detached headed Chromium worker for a configured listing."""

    studio_root = Path(root).expanduser().resolve()
    store = LocalEventStudioRuleStore(
        root=studio_root,
        source_config_path=source_config_path,
    )
    safe_source, canonical_url = store._binding(source_id, listing_url)
    current = _read_state(studio_root, safe_source, canonical_url)
    if _alive(int(current.get("pid") or 0)):
        return {**current, "ok": True, "already_running": True}

    worker = Path(__file__).resolve().parents[1] / "jobs" / "local_event_studio_live.py"
    log = _live_dir(studio_root) / f"{_key(safe_source, canonical_url)}.log"
    environment = os.environ.copy()
    environment["INFOSCREEN_ENV_DIR"] = str(studio_root.parent)
    with log.open("ab") as handle:
        process = subprocess.Popen(
            [sys.executable, str(worker), safe_source, canonical_url],
            cwd=str(worker.parents[1]),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=environment,
        )
    state = _write_state(
        studio_root,
        safe_source,
        canonical_url,
        pid=process.pid,
        status="starting",
        current_url=canonical_url,
        started_at=_now().isoformat(),
        log_path=str(log),
        error=None,
    )
    return {**state, "ok": True, "already_running": False}


def _source_record(path: Path, source_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload.get("sources") or []:
        if isinstance(item, dict) and item.get("id") == source_id:
            return dict(item)
    raise ValueError(f"source not found: {source_id}")


def _page_role(url: str, listing_url: str) -> str:
    current = urlsplit(url)
    listing = urlsplit(canonical_listing_url(listing_url))
    return (
        "listing"
        if (
            current.netloc.lower(),
            current.path.rstrip("/"),
        )
        == (
            listing.netloc.lower(),
            listing.path.rstrip("/"),
        )
        else "detail"
    )


def _snapshot_and_test(
    page: Any,
    context: Any,
    store: LocalEventStudioRuleStore,
    source: dict[str, Any],
    source_id: str,
    listing_url: str,
    studio_root: Path,
) -> dict[str, Any]:
    if _page_role(str(page.url), listing_url) != "listing":
        raise ValueError("Return to the configured listing first")

    draft = store.load_draft(source_id, listing_url)
    if draft is None:
        raise ValueError("Select card, detail link and required fields first")

    dom = page.evaluate(DOM_EVIDENCE_JS, {"maxElements": 6000})
    captured = _now()
    snapshot_id = (
        captured.strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + hashlib.sha256(listing_url.encode("utf-8")).hexdigest()[:10]
    )
    metadata = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "source_name": source.get("name"),
        "listing_url": listing_url,
        "final_url": str(page.url),
        "page_title": page.title(),
        "captured_at": captured.isoformat(),
        "prepare": {"mode": "operator_live_browser"},
        "dom_element_count": int(dom.get("element_count") or 0),
        "dom_truncated": bool(dom.get("truncated")),
        "assets": {
            "page.png": "page.png",
            "page.html": "page.html",
            "dom.json": "dom.json",
            "metadata.json": "metadata.json",
        },
    }
    snapshot = write_snapshot(
        studio_root,
        metadata,
        screenshot=page.screenshot(full_page=True, type="png"),
        html=page.content(),
        dom=dom,
    )
    result = validate_current_listing(
        page,
        context,
        draft,
        source,
    )
    test = _write_test_run(studio_root, result, snapshot_id)
    return {**snapshot, "test_result": test}


def run_live_session(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> int:
    """Run one headed browser session until the operator closes all pages."""

    studio_root = Path(root).expanduser().resolve()
    config_path = Path(source_config_path).expanduser().resolve()
    store = LocalEventStudioRuleStore(
        root=studio_root,
        source_config_path=config_path,
    )
    safe_source, canonical_url = store._binding(source_id, listing_url)
    source = _source_record(config_path, safe_source)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _write_state(
            studio_root,
            safe_source,
            canonical_url,
            status="failed",
            error=f"missing_playwright:{exc}",
        )
        return 2

    executable = find_browser_executable()
    if not executable:
        _write_state(
            studio_root,
            safe_source,
            canonical_url,
            status="failed",
            error="missing_system_chromium",
        )
        return 3

    binding = "__infoscreenStudioBinding"
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(
                    _live_dir(studio_root)
                    / f"{_key(safe_source, canonical_url)}-profile"
                ),
                headless=False,
                executable_path=executable,
                viewport=None,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                ],
            )
            page = context.pages[0] if context.pages else context.new_page()

            def callback(source_binding: Any, payload: Any) -> dict[str, Any]:
                data = dict(payload or {})
                current_page = source_binding["page"]
                action = data.get("action")
                if action == "clear_draft":
                    store.delete_draft(safe_source, canonical_url)
                    return {"ok": True, "message": "Draft cleared."}
                if action == "capture_listing":
                    snapshot = _snapshot_and_test(
                        current_page,
                        context,
                        store,
                        source,
                        safe_source,
                        canonical_url,
                        studio_root,
                    )
                    test = snapshot["test_result"]
                    return {
                        "ok": True,
                        "message": (
                            f"Validation {'passed' if test['publishable'] else 'failed'}: "
                            f"{test['accepted_count']} confirmed details."
                        ),
                    }
                if action == "select":
                    data["page_role"] = _page_role(
                        str(current_page.url),
                        canonical_url,
                    )
                    draft = save_live_selection(
                        store,
                        safe_source,
                        canonical_url,
                        data,
                    )
                    return {
                        "ok": True,
                        "message": (
                            f"Saved {data.get('mode')}: "
                            f"{data.get('selector') or ''}"
                        ),
                        "card_selector": (
                            draft.card.selector
                            if draft.card is not None
                            else ""
                        ),
                    }
                raise ValueError("unsupported action")

            context.expose_binding(binding, callback)

            def install(target: Any) -> None:
                try:
                    if not host_allowed(str(target.url), source):
                        return
                    target.evaluate(
                        OVERLAY_JS,
                        {
                            "binding": binding,
                            "listing_url": canonical_url,
                        },
                    )
                    draft = store.load_draft(safe_source, canonical_url)
                    if draft is not None and draft.card is not None:
                        target.evaluate(
                            "selector => window.__infoscreenCardSelector = selector",
                            draft.card.selector,
                        )
                except Exception:
                    return

            def configure(target: Any) -> None:
                target.on("domcontentloaded", lambda: install(target))
                target.on(
                    "framenavigated",
                    lambda frame: (
                        _write_state(
                            studio_root,
                            safe_source,
                            canonical_url,
                            pid=os.getpid(),
                            status="running",
                            current_url=str(target.url),
                            error=None,
                        )
                        if frame == target.main_frame
                        else None
                    ),
                )

            for target in context.pages:
                configure(target)
            context.on("page", configure)

            try:
                page.goto(
                    canonical_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception:
                page.goto(canonical_url, wait_until="commit", timeout=30000)
            page.wait_for_timeout(600)
            install(page)
            _write_state(
                studio_root,
                safe_source,
                canonical_url,
                pid=os.getpid(),
                status="running",
                current_url=str(page.url),
                error=None,
            )
            try:
                while context.pages:
                    time.sleep(0.5)
            finally:
                _write_state(
                    studio_root,
                    safe_source,
                    canonical_url,
                    status="closed",
                )
                context.close()
        return 0
    except Exception as exc:
        _write_state(
            studio_root,
            safe_source,
            canonical_url,
            status="failed",
            error=f"{type(exc).__name__}:{str(exc)[:1000]}",
        )
        return 4


__all__ = [
    "_read_state",
    "run_live_session",
    "start_live_session",
]
