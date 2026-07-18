from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from .extract import label_dates
from .studio_collect import StudioBrowser, apply_published_studio_rules

SURFACE_DIR = Path(__file__).resolve().parents[1]


def runtime_env_dir() -> Path:
    """Resolve the active machine-local runtime root shared by server and jobs."""

    return Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
    ).expanduser().resolve()


def _synchronize_event_dates(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("source_type") != "studio_published_rule":
        return event
    dates = label_dates(str(event.get("when") or ""))
    if not dates:
        return event
    updated = dict(event)
    updated["start_date"] = min(dates).isoformat()
    updated["end_date"] = max(dates).isoformat()
    return updated


def _enforce_live_rule_health(payload: dict[str, Any]) -> dict[str, Any]:
    output = dict(payload)
    debug_rows: list[dict[str, Any]] = []
    partial = bool(output.get("partial"))
    for raw in output.get("debug_by_source") or []:
        row = dict(raw) if isinstance(raw, dict) else raw
        if not isinstance(row, dict) or row.get("adapter") != "studio_published_rule":
            debug_rows.append(row)
            continue
        fatal_errors = list(row.get("fatal_errors") or [])
        accepted = int(row.get("accepted") or 0)
        if fatal_errors or accepted <= 0:
            row["status"] = "failed"
            row["complete"] = False
            row.setdefault(
                "error",
                "studio_rule_no_accepted_events" if accepted <= 0 else "studio_rule_evaluation_failed",
            )
            partial = True
        debug_rows.append(row)
    output["debug_by_source"] = debug_rows
    if partial:
        output["partial"] = True
    return output


def apply_runtime_studio_rules(
    payload: dict[str, Any],
    *,
    browser_factory: Callable[[], StudioBrowser] = StudioBrowser,
) -> dict[str, Any]:
    """Apply published rules, synchronize final fields, and enforce source health."""

    output = apply_published_studio_rules(
        payload,
        root=runtime_env_dir() / "local_event_studio",
        source_config_path=SURFACE_DIR / "conf" / "event_sources.json",
        browser_factory=browser_factory,
    )
    output = dict(output)
    output["results"] = [
        _synchronize_event_dates(dict(item))
        for item in output.get("results") or []
        if isinstance(item, dict)
    ]
    output["count"] = len(output["results"])
    return _enforce_live_rule_health(output)


__all__ = ["apply_runtime_studio_rules", "runtime_env_dir"]
