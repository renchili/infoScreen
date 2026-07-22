#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("LOCAL_EVENTS_MAX_SECONDS", "900")
os.environ.setdefault("LOCAL_EVENTS_SOURCE_CONCURRENCY", "4")
os.environ.setdefault("LOCAL_EVENTS_SOURCE_TIMEOUT_SECONDS", "780")
os.environ.setdefault("LOCAL_EVENTS_MAX_LISTING_PAGES", "2")
os.environ.setdefault("LOCAL_EVENTS_LOAD_MORE_ROUNDS", "24")
os.environ.setdefault("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "180")
os.environ.setdefault("LOCAL_EVENTS_NAV_TIMEOUT_MS", "25000")
os.environ.setdefault("LOCAL_EVENTS_DOM_TIMEOUT_MS", "25000")
# The listing-authority pipeline performs the only supported detail pass.
# Disable the legacy NHB pre-enrichment to avoid reading every detail twice.
os.environ.setdefault("LOCAL_EVENTS_NHB_DETAIL_LIMIT", "0")
os.environ.setdefault("LOCAL_EVENTS_NHB_DETAIL_TIMEOUT_MS", "8000")
# Every admitted card may require its detail page for date and venue fields.
# Do not impose a smaller arbitrary detail limit than the run's Event budget.
os.environ.setdefault(
    "LOCAL_EVENTS_DETAIL_LIMIT",
    os.environ["LOCAL_EVENTS_MAX_TOTAL_EVENTS"],
)
os.environ.setdefault("LOCAL_EVENTS_DETAIL_TIMEOUT_MS", "60000")
os.environ.setdefault("LOCAL_EVENTS_PAGE_SCREENSHOTS", "0")
os.environ.setdefault("LOCAL_EVENTS_CARD_SCREENSHOTS", "0")

import local_events_runtime as _local_events_runtime  # noqa: E402
from local_events_runtime import detail_date_authority  # noqa: E402
from local_events_runtime import gardens_field_authority  # noqa: E402
from local_events_runtime import listing_only_output_authority  # noqa: E402
from local_events_runtime import listing_url_authority  # noqa: E402
from local_events_runtime import mandai_listing_authority  # noqa: E402
from local_events_runtime import open_ended_date_authority  # noqa: E402
from local_events_runtime.output import normalize_payload  # noqa: E402

detail_date_authority.apply()
open_ended_date_authority.apply()
gardens_field_authority.apply()
mandai_listing_authority.apply()
listing_url_authority.apply()
listing_only_output_authority.apply()
collect_events = _local_events_runtime.collect_events

SURFACE_DIR = Path(__file__).resolve().parents[1]
ENV_DIR = Path(
    os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
).expanduser().resolve()
CONF_DIR = SURFACE_DIR / "conf"
CONFIG = CONF_DIR / "event_sources.json"
COLLECTOR_OUT = ENV_DIR / "local_event_search_results.partial.json"
DEBUG_DIR = ENV_DIR / "local_event_debug_cards"
DEFAULT_LOCATION = "Punggol Singapore"
TIMEOUT_REASON_MARKERS = ("deadline", "budget_exhausted", "timeout")


def source_completion(debug: dict) -> tuple[str, bool]:
    listing_urls = debug.get("listing_urls")
    expected = len(listing_urls) if isinstance(listing_urls, list) else 0
    try:
        fetched = int(debug.get("listing_fetched") or 0)
    except (TypeError, ValueError):
        fetched = 0

    if debug.get("complete") is True or (expected > 0 and fetched >= expected):
        return "complete", True

    reason_counts = debug.get("reason_counts")
    reasons = [str(value).lower() for value in reason_counts] if isinstance(reason_counts, dict) else []
    previews = debug.get("not_output_preview")
    if isinstance(previews, list):
        reasons.extend(
            str(item.get("reason") or "").lower()
            for item in previews
            if isinstance(item, dict)
        )

    if any("not_started" in reason for reason in reasons):
        return "not_started", False
    if any(marker in reason for reason in reasons for marker in TIMEOUT_REASON_MARKERS):
        return "timed_out", False
    if fetched > 0:
        return "partial", False
    return "failed", False


def annotate_source_completion(payload: dict) -> dict:
    annotated = dict(payload)
    raw_debug = payload.get("debug_by_source")
    debug_rows = raw_debug if isinstance(raw_debug, list) else []
    source_count = int(payload.get("source_count") or len(debug_rows) or 0)
    completed = 0
    status_counts: dict[str, int] = {}
    normalized_debug = []

    for raw in debug_rows:
        row = dict(raw) if isinstance(raw, dict) else {}
        status, complete = source_completion(row)
        row["status"] = status
        row["complete"] = complete
        normalized_debug.append(row)
        status_counts[status] = status_counts.get(status, 0) + 1
        if complete:
            completed += 1

    missing_rows = max(0, source_count - len(normalized_debug))
    if missing_rows:
        status_counts["not_started"] = status_counts.get("not_started", 0) + missing_rows

    annotated["source_count"] = source_count
    annotated["debug_by_source"] = normalized_debug
    annotated["completed_source_count"] = completed
    annotated["incomplete_source_count"] = max(0, source_count - completed)
    annotated["source_status_counts"] = status_counts
    annotated["partial"] = bool(source_count and completed < source_count)
    return annotated


def write_collector_snapshot(payload: dict) -> dict:
    """Persist crawler output as diagnostics without touching the display runtime."""

    snapshot = annotate_source_completion(normalize_payload(payload))
    snapshot["write_policy"] = "collector_diagnostics_only"
    snapshot["display_runtime_unchanged"] = True
    snapshot["display_runtime"] = "local_event_search_results.json"
    COLLECTOR_OUT.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot


def self_test() -> int:
    payload = annotate_source_completion(
        normalize_payload(collect_events(CONFIG, DEFAULT_LOCATION, DEBUG_DIR))
    )
    assert payload["extractor"] == "listing-authoritative-v52"
    assert payload["version"] == 52
    assert payload["text_normalizer"] == "plain-text-v1"
    assert isinstance(payload.get("results"), list)
    assert isinstance(payload.get("debug_by_source"), list)
    assert isinstance(payload.get("partial"), bool)
    print("local-event collector diagnostic self-test passed")
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
    payload = write_collector_snapshot(
        collect_events(CONFIG, location, DEBUG_DIR)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
