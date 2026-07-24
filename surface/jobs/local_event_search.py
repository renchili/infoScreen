#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import local_events_runtime as _local_events_runtime  # noqa: E402
from local_events_runtime import complete_collection_authority  # noqa: E402
from local_events_runtime import detail_date_authority  # noqa: E402
from local_events_runtime import detail_payload_authority  # noqa: E402
from local_events_runtime import detail_summary_authority  # noqa: E402
from local_events_runtime import gardens_field_authority  # noqa: E402
from local_events_runtime import listing_membership_authority  # noqa: E402
from local_events_runtime import listing_only_output_authority  # noqa: E402
from local_events_runtime import listing_provenance_authority  # noqa: E402
from local_events_runtime import listing_url_authority  # noqa: E402
from local_events_runtime import mandai_listing_authority  # noqa: E402
from local_events_runtime import open_detail_fields_authority  # noqa: E402
from local_events_runtime import open_ended_date_authority  # noqa: E402
from local_events_runtime import review_summary_authority  # noqa: E402
from local_events_runtime.event_review import EventReviewStore  # noqa: E402
from local_events_runtime.output import normalize_payload  # noqa: E402
from local_events_runtime.review_publish_authority import (  # noqa: E402
    COLLECTOR_RUNTIME_FILENAME,
    atomic_write,
    load_collector_snapshot,
    merge_review_state,
    write_collector_snapshot,
)

complete_collection_authority.apply()
detail_date_authority.apply()
detail_payload_authority.apply()
detail_summary_authority.apply()
open_ended_date_authority.apply()
open_detail_fields_authority.apply()
gardens_field_authority.apply()
listing_provenance_authority.apply()
listing_membership_authority.apply()
mandai_listing_authority.apply()
listing_url_authority.apply()
listing_only_output_authority.apply()
review_summary_authority.apply()
collect_events = _local_events_runtime.collect_events

SURFACE_DIR = Path(__file__).resolve().parents[1]
ENV_DIR = Path(
    os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
).expanduser().resolve()
CONF_DIR = SURFACE_DIR / "conf"
CONFIG = CONF_DIR / "event_sources.json"
OUT = ENV_DIR / "local_event_search_results.json"
COLLECTOR_OUT = ENV_DIR / COLLECTOR_RUNTIME_FILENAME
PARTIAL_OUT = ENV_DIR / "local_event_search_results.partial.json"
REVIEW_ROOT = ENV_DIR / "local_event_review"
DEBUG_DIR = ENV_DIR / "local_event_debug_cards"
DEFAULT_LOCATION = "Punggol Singapore"
VERIFIED_POLICY = "official-listing-authority-v1"
TIMEOUT_REASON_MARKERS = ("deadline", "budget_exhausted", "timeout")


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def result_count(payload: dict) -> int:
    results = payload.get("results")
    return len(results) if isinstance(results, list) else int(payload.get("count") or 0)


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
    reasons = [
        str(value).lower()
        for value in reason_counts
    ] if isinstance(reason_counts, dict) else []
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


def verified_previous_payload(payload: dict) -> dict:
    """Keep previously verified collector rows exactly as persisted."""

    verified = dict(payload)
    results = payload.get("results")
    if not isinstance(results, list):
        return verified
    verified_results = [
        dict(item)
        for item in results
        if isinstance(item, dict)
        and item.get("candidate_policy") == VERIFIED_POLICY
    ]
    verified["results"] = verified_results
    verified["count"] = len(verified_results)
    verified["legacy_unverified_removed"] = len(results) - len(verified_results)
    return verified


def review_store() -> EventReviewStore:
    return EventReviewStore(root=REVIEW_ROOT, config_path=CONFIG)


def write_payload(
    payload: dict,
    store: EventReviewStore | None = None,
) -> dict:
    """Persist producer output, then publish one deterministic Review projection.

    ``local_event_collector_results.json`` is the producer-owned base. The kiosk
    primary is always rebuilt from that snapshot plus current Review decisions.
    A smaller incomplete crawl remains partial evidence and cannot replace a larger
    verified collector snapshot.
    """

    collector = annotate_source_completion(normalize_payload(payload))
    active_store = store or review_store()
    previous = verified_previous_payload(load_collector_snapshot(active_store))
    previous_system_count = result_count(previous)
    new_system_count = result_count(collector)

    if collector["partial"]:
        partial = {
            **collector,
            "ok": False,
            "write_policy": "partial_collector_evidence",
            "display_runtime": str(OUT),
            "collector_runtime": str(COLLECTOR_OUT),
        }
        atomic_write(PARTIAL_OUT, partial)

    if collector["partial"] and previous_system_count > new_system_count:
        display = merge_review_state(previous, active_store)
        display["write_policy"] = "kept_previous_verified_result_with_review"
        display["previous_system_count"] = previous_system_count
        display["partial_collector_count"] = new_system_count
        atomic_write(OUT, display)

        partial = read_json(PARTIAL_OUT)
        partial["write_policy"] = "kept_previous_verified_result"
        partial["previous_system_count"] = previous_system_count
        partial["display_count"] = result_count(display)
        atomic_write(PARTIAL_OUT, partial)
        return display

    persisted_collector = write_collector_snapshot(active_store, collector)
    display = merge_review_state(persisted_collector, active_store)
    display["write_policy"] = (
        "collector_partial_with_review"
        if collector["partial"]
        else "collector_complete_with_review"
    )
    atomic_write(OUT, display)
    return display


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
    print("local-event listing-authoritative self-test passed")
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
    display = write_payload(collect_events(CONFIG, location, DEBUG_DIR))
    print(json.dumps(display, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
