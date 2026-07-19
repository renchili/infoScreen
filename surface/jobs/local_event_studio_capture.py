#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SURFACE_DIR = Path(__file__).resolve().parents[1]
if str(SURFACE_DIR) not in sys.path:
    sys.path.insert(0, str(SURFACE_DIR))

from local_events_runtime.studio_live import start_live_session


def studio_root() -> Path:
    env_dir = Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
    ).expanduser().resolve()
    return env_dir / "local_event_studio"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open one configured Local Events listing in the operator-controlled Studio browser.",
    )
    parser.add_argument("source_id", help="Configured source ID from event_sources.json")
    parser.add_argument("listing_url", help="Configured official listing URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        session = start_live_session(
            args.source_id,
            args.listing_url,
            root=studio_root(),
            source_config_path=SURFACE_DIR / "conf" / "event_sources.json",
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "studio_live_browser_start_failed",
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 1

    snapshot_compat = {
        "schema_version": 1,
        "snapshot_id": f"live-{session.get('pid')}",
        "source_id": session["source_id"],
        "source_name": None,
        "listing_url": session["listing_url"],
        "final_url": session.get("current_url") or session["listing_url"],
        "page_title": "Live browser session",
        "captured_at": session.get("started_at") or session.get("updated_at"),
        "prepare": {
            "mode": "operator_live_browser",
            "pid": session.get("pid"),
            "already_running": bool(session.get("already_running")),
        },
        "dom_element_count": 0,
        "dom_truncated": False,
        "assets": {},
        "mode": "operator_live_browser",
        "session": session,
    }
    print(
        json.dumps(
            {"ok": True, "snapshot": snapshot_compat, "session": session},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
