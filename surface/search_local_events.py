#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_events_runtime import collect_events

SURFACE_DIR = Path(__file__).resolve().parent
ENV_DIR = SURFACE_DIR / ".env"
CONF_DIR = SURFACE_DIR / "conf"
CONFIG = CONF_DIR / "event_sources.json"
OUT = ENV_DIR / "local_event_search_results.json"
DEBUG_DIR = ENV_DIR / "local_event_debug_cards"
DEFAULT_LOCATION = "Punggol Singapore"


def self_test() -> int:
    payload = collect_events(CONFIG, DEFAULT_LOCATION, DEBUG_DIR)
    assert payload["extractor"] == "rendered-dom-card-v40"
    assert isinstance(payload.get("results"), list)
    assert isinstance(payload.get("debug_by_source"), list)
    print("local-event rendered DOM self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("location", nargs="*")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    location = " ".join(args.location).strip() or DEFAULT_LOCATION
    ENV_DIR.mkdir(exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    payload = collect_events(CONFIG, location, DEBUG_DIR)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
