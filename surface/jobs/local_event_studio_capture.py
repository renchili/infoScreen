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

from local_events_runtime.studio_capture import capture_snapshot


def studio_root() -> Path:
    env_dir = Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
    ).expanduser().resolve()
    return env_dir / "local_event_studio"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one configured Local Events listing for the local Studio.",
    )
    parser.add_argument("source_id", help="Configured source ID from event_sources.json")
    parser.add_argument("listing_url", help="Configured official listing URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        snapshot = capture_snapshot(
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
                    "error": "studio_capture_failed",
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 1

    print(
        json.dumps(
            {"ok": True, "snapshot": snapshot},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
