#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SURFACE_DIR = Path(__file__).resolve().parents[1]
if str(SURFACE_DIR) not in sys.path:
    sys.path.insert(0, str(SURFACE_DIR))

from local_events_runtime.studio_live import run_live_session


def studio_root() -> Path:
    env_dir = Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
    ).expanduser().resolve()
    return env_dir / "local_event_studio"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one operator-controlled Local Event Studio browser session.",
    )
    parser.add_argument("source_id")
    parser.add_argument("listing_url")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_live_session(
        args.source_id,
        args.listing_url,
        root=studio_root(),
        source_config_path=SURFACE_DIR / "conf" / "event_sources.json",
    )


if __name__ == "__main__":
    raise SystemExit(main())
