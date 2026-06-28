#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import local_events_engine as engine

SURFACE_DIR = Path(__file__).resolve().parent
ENV_DIR = SURFACE_DIR / ".env"
CONF_DIR = SURFACE_DIR / "conf"

engine.APP_ROOT = SURFACE_DIR
engine.REGISTRY = CONF_DIR / "official_source_registry.json"
engine.OUT = ENV_DIR / "local_event_search_results.json"


def main() -> int:
    ENV_DIR.mkdir(exist_ok=True)
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
