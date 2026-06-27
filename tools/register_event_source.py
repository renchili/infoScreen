#!/usr/bin/env python3
"""Register one confirmed institution event source.

This script is deliberately confirmation-driven. It does not auto-promote the
best discovery candidate. The caller must pass the confirmed official site and
one or more confirmed event listing URLs.

Workflow:
  1. Run tools/discover_event_sources.py for one institution.
  2. Inspect the output and confirm the official site + listing URL manually.
  3. Run this script to upsert that confirmed source into event_source_registry.json.

Example:
  python3 tools/register_event_source.py \
    --name "Asian Civilisations Museum" \
    --canonical-site https://www.acm.nhb.gov.sg/ \
    --listing-url 'https://www.acm.nhb.gov.sg/whats-on/overview?category=Exhibitions%2CLectures%2CProgrammes%2CGuided+Tours&time=Today%2CUpcoming' \
    --discovery discovered_event_sources.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY = Path("event_source_registry.json")


def normalize_url(raw: str) -> str:
    value = (raw or "").strip()
    if value.startswith("//"):
        value = "https:" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"invalid URL: {raw}")
    path = parsed.path or "/"
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    )
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))


def canonical_root(raw: str) -> str:
    parsed = urllib.parse.urlparse(normalize_url(raw))
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), "/", "", "", ""))


def host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def same_site(url: str, canonical_site: str) -> bool:
    a = host(url)
    b = host(canonical_site)
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": 1,
            "policy": {
                "source_scope": "official_site_only",
                "third_party_candidates": "discovery_diagnostics_only",
                "registration_rule": "Register only manually confirmed canonical official sites and same-site event listing URLs.",
            },
            "institutions": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def load_discovery(path: str | None, name: str, canonical_site: str) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"discovery file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    for item in data.get("results", []):
        if str(item.get("institution", "")).strip().lower() != name.strip().lower():
            continue
        if same_site(str(item.get("official_site", "")), canonical_site):
            return {
                "score": item.get("score", 0),
                "evidence": item.get("evidence", []),
                "discovered_official_site": item.get("official_site", ""),
                "discovered_event_listing_url": item.get("event_listing_url", ""),
            }
    return {}


def upsert(registry: dict[str, Any], entry: dict[str, Any]) -> None:
    institutions = registry.setdefault("institutions", [])
    key = entry["name"].strip().lower()
    for idx, item in enumerate(institutions):
        if str(item.get("name", "")).strip().lower() == key:
            institutions[idx] = entry
            return
    institutions.append(entry)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--name", required=True)
    parser.add_argument("--canonical-site", required=True)
    parser.add_argument("--listing-url", action="append", required=True, help="Confirmed official event listing URL. Can be repeated.")
    parser.add_argument("--discovery", help="Optional discovery JSON to copy score/evidence from after manual confirmation.")
    parser.add_argument("--detail-example", action="append", default=[], help="Optional confirmed same-site detail URL evidence. Can be repeated.")
    args = parser.parse_args()

    canonical_site = canonical_root(args.canonical_site)
    listing_urls = [normalize_url(url) for url in args.listing_url]
    detail_examples = [normalize_url(url) for url in args.detail_example]

    for url in listing_urls + detail_examples:
        if not same_site(url, canonical_site):
            raise SystemExit(f"refusing non-official URL for {args.name}: {url} is not under {canonical_site}")

    discovery = load_discovery(args.discovery, args.name, canonical_site)
    entry = {
        "name": args.name.strip(),
        "status": "confirmed",
        "canonical_site": canonical_site,
        "allowed_domains": [host(canonical_site)],
        "event_listing_urls": listing_urls,
        "confirmed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "confirmation": {
            "method": "manual_review_after_source_discovery",
            "discovery": discovery,
            "confirmed_detail_examples": detail_examples,
        },
    }

    registry_path = Path(args.registry)
    registry = load_registry(registry_path)
    upsert(registry, entry)
    registry["institutions"] = sorted(registry.get("institutions", []), key=lambda x: str(x.get("name", "")).lower())
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
