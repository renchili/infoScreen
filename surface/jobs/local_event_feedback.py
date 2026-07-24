#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SURFACE_DIR = Path(__file__).resolve().parents[1]
if str(SURFACE_DIR) not in sys.path:
    sys.path.insert(0, str(SURFACE_DIR))

from local_events_runtime.event_feedback import run_feedback_browser


def review_root() -> Path:
    env_dir = Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
    ).expanduser().resolve()
    return env_dir / "local_event_review"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Open one official Event listing for interactive user feedback.",
    )
    parser.add_argument("source_id")
    parser.add_argument("listing_url")
    args = parser.parse_args(argv)
    return run_feedback_browser(
        args.source_id,
        args.listing_url,
        root=review_root(),
        config_path=SURFACE_DIR / "conf" / "event_sources.json",
    )


if __name__ == "__main__":
    raise SystemExit(main())
