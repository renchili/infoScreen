#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("LOCAL_EVENTS_MAX_SECONDS", "520")
os.environ.setdefault("LOCAL_EVENTS_SOURCE_CONCURRENCY", "3")
os.environ.setdefault("LOCAL_EVENTS_SOURCE_TIMEOUT_SECONDS", "95")
os.environ.setdefault("LOCAL_EVENTS_MAX_LISTING_PAGES", "2")
os.environ.setdefault("LOCAL_EVENTS_LOAD_MORE_ROUNDS", "2")
os.environ.setdefault("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "180")
os.environ.setdefault("LOCAL_EVENTS_NAV_TIMEOUT_MS", "25000")
os.environ.setdefault("LOCAL_EVENTS_DOM_TIMEOUT_MS", "25000")
os.environ.setdefault("LOCAL_EVENTS_NHB_DETAIL_LIMIT", "18")
os.environ.setdefault("LOCAL_EVENTS_NHB_DETAIL_TIMEOUT_MS", "16000")
os.environ.setdefault("LOCAL_EVENTS_PAGE_SCREENSHOTS", "0")
os.environ.setdefault("LOCAL_EVENTS_CARD_SCREENSHOTS", "0")

from local_events_runtime import collect_events  # noqa: E402

SURFACE_DIR = Path(__file__).resolve().parents[1]
ENV_DIR = SURFACE_DIR / ".env"
CONF_DIR = SURFACE_DIR / "conf"
CONFIG = CONF_DIR / "event_sources.json"
OUT = ENV_DIR / "local_event_search_results.json"
PARTIAL_OUT = ENV_DIR / "local_event_search_results.partial.json"
DEBUG_DIR = ENV_DIR / "local_event_debug_cards"
DEFAULT_LOCATION = "Punggol Singapore"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def result_count(payload: dict) -> int:
    results = payload.get("results")
    return len(results) if isinstance(results, list) else int(payload.get("count") or 0)


def debug_count(payload: dict) -> int:
    debug = payload.get("debug_by_source")
    return len(debug) if isinstance(debug, list) else 0


def is_partial(payload: dict) -> bool:
    source_count = int(payload.get("source_count") or 0)
    return bool(source_count and debug_count(payload) < source_count)


def write_payload(payload: dict) -> None:
    old = read_json(OUT)
    new_count = result_count(payload)
    old_count = result_count(old)

    if is_partial(payload) and old_count > new_count:
        payload = {
            **payload,
            "ok": False,
            "partial": True,
            "write_policy": "kept_previous_complete_result",
            "previous_count": old_count,
        }
        PARTIAL_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    payload = {**payload, "partial": is_partial(payload)}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def self_test() -> int:
    payload = collect_events(CONFIG, DEFAULT_LOCATION, DEBUG_DIR)
    assert payload["extractor"] == "rendered-dom-card-v46-source-order"
    assert payload["version"] == 46
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
    write_payload(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
