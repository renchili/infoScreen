from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import extract as _extract
from . import source_overrides

_applied = False
_base_render = None
_base_collect = None


def _review_state_path() -> Path:
    surface_dir = Path(__file__).resolve().parents[1]
    env_dir = Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(surface_dir / ".env"))
    ).expanduser()
    return env_dir / "local_event_review" / "state.json"


def _load_state() -> dict[str, Any]:
    path = _review_state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _canonical_url(value: object) -> str:
    raw = _extract.clean(value)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )


def _same_url(left: object, right: object) -> bool:
    first = _canonical_url(left)
    second = _canonical_url(right)
    return bool(first and first == second)


def _feedback_title(text: str, href: str) -> str:
    for line in _extract.lines(text):
        title = _extract.normalise_title(line)
        if (
            title
            and len(title) >= 4
            and not _extract.DATE_LINE_RE.search(title)
            and not _extract.GENERIC_TITLE_RE.match(title)
        ):
            return _extract.short(title, 140)
    return _extract.title_from_url(href)


def _feedback_card(
    source: dict[str, Any],
    listing_url: str,
    row: dict[str, Any],
) -> dict[str, Any] | None:
    href = _canonical_url(row.get("href"))
    if not source_overrides.canonical_detail_url(source, href):
        return None

    text = str(row.get("text") or "").strip()
    title = _feedback_title(text, href)
    if not title:
        return None

    lines = _extract.lines(text)
    if title not in lines:
        lines.insert(0, title)
    digest = hashlib.sha256(
        "\n".join(
            [
                str(source.get("id") or ""),
                _canonical_url(listing_url),
                str(row.get("selector") or ""),
                str(row.get("selector_index") or 0),
                href,
            ]
        ).encode("utf-8")
    ).hexdigest()[:20]

    return {
        "id": f"{source.get('id') or 'source'}-operator-{digest}",
        "url": href,
        "link_text": title,
        "headings": [title],
        "image_alts": [],
        "text": "\n".join(lines),
        "text_lines": lines,
        "detail_url_count": 1,
        "detail_urls": [href],
        "page_index": 0,
        "page_url": href,
        "rect": dict(row.get("document_position") or {}),
        "role": "detail",
        "extraction_mode": "operator_feedback_card",
        "listing_evidence": source_overrides.LISTING_EVIDENCE,
        "listing_url": _canonical_url(listing_url),
        "listing_card_id": f"operator-feedback-{digest}",
        "listing_extraction_mode": "operator_feedback_card",
        "operator_feedback_id": str(row.get("feedback_id") or ""),
        "screenshot": "",
    }


def _matching_feedback(
    source: dict[str, Any],
    listing_url: str,
) -> list[dict[str, Any]]:
    source_id = str(source.get("id") or "")
    canonical_listing = _canonical_url(listing_url)
    state = _load_state()
    rows = state.get("feedback")
    if not isinstance(rows, list):
        return []

    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("source_id") or "") != source_id:
            continue
        if not _same_url(raw.get("listing_url"), canonical_listing):
            continue
        card = _feedback_card(source, canonical_listing, raw)
        if card is None:
            continue
        key = _canonical_url(card.get("url"))
        if not key or key in seen:
            continue
        seen.add(key)
        cards.append(card)
    return cards


def _render_with_feedback(
    source: dict[str, Any],
    url: str,
    debug_dir,
    max_cards: int = 60,
):
    rendered = dict(
        _base_render(source, url, debug_dir, max_cards=max_cards)
    )
    feedback_cards = _matching_feedback(source, url)
    original_cards = [
        card
        for card in rendered.get("cards") or []
        if isinstance(card, dict)
    ]

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in [*feedback_cards, *original_cards]:
        key = _canonical_url(card.get("url"))
        if not key:
            key = (
                _extract.clean(card.get("url"))
                + "\n"
                + _extract.clean(card.get("text"))[:500]
            )
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(card)
        if len(merged) >= max_cards:
            break

    rendered["cards"] = merged
    rendered["operator_feedback"] = {
        "matched": len(feedback_cards),
        "state_path": str(_review_state_path()),
    }
    return rendered


def _confirmed_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    if str(raw.get("decision") or "") != "confirmed":
        return None

    title = _extract.normalise_title(raw.get("title"))
    when = _extract.clean(raw.get("when"))
    url = _canonical_url(raw.get("detail_url"))
    if not title or not when or not url:
        return None

    dates = _extract.label_dates(when)
    source_name = _extract.clean(raw.get("source_name")) or _extract.clean(
        raw.get("source_id")
    )
    where = _extract.clean(raw.get("where")) or source_name
    summary = _extract.clean(raw.get("summary")) or (
        "Confirmed by the operator from the official activity listing."
    )
    return {
        "title": _extract.short(title, 140),
        "when": when,
        "where": where,
        "host": source_name,
        "source_name": source_name,
        "url": url,
        "summary": summary,
        "start_date": _extract.best_start_date(when),
        "end_date": max(dates).isoformat() if len(dates) >= 2 else "",
        "kind": "event",
        "source_type": "operator_confirmed_official_listing",
        "candidate_policy": "official-listing-authority-v1",
        "listing_url": _canonical_url(raw.get("listing_url")),
        "listing_card_id": str(raw.get("candidate_id") or ""),
        "operator_review_decision": "confirmed",
    }


def _merge_confirmed_events(payload: dict[str, Any]) -> dict[str, Any]:
    state = _load_state()
    rows = state.get("events")
    confirmed = [
        event
        for raw in (rows if isinstance(rows, list) else [])
        if isinstance(raw, dict)
        if (event := _confirmed_event(raw)) is not None
    ]

    results = [
        dict(item)
        for item in payload.get("results") or []
        if isinstance(item, dict)
    ]
    by_url = {
        _canonical_url(item.get("url")): index
        for index, item in enumerate(results)
        if _canonical_url(item.get("url"))
    }
    added = 0
    updated = 0

    for event in confirmed:
        key = _canonical_url(event.get("url"))
        existing_index = by_url.get(key)
        if existing_index is None:
            by_url[key] = len(results)
            results.append(event)
            added += 1
            continue

        current = dict(results[existing_index])
        for field, value in event.items():
            if value not in {"", None}:
                current[field] = value
        results[existing_index] = current
        updated += 1

    source_order = {
        _extract.norm_key((row or {}).get("title")): index
        for index, row in enumerate(payload.get("sources") or [])
        if isinstance(row, dict)
    }
    indexed = list(enumerate(results))
    indexed.sort(
        key=lambda pair: (
            source_order.get(
                _extract.norm_key(
                    pair[1].get("source_name") or pair[1].get("host")
                ),
                10_000,
            ),
            pair[0],
        )
    )

    merged = dict(payload)
    merged["results"] = [item for _, item in indexed]
    merged["count"] = len(results)
    merged["review_authority"] = {
        "confirmed_in_state": len(confirmed),
        "added": added,
        "updated": updated,
        "feedback_state_path": str(_review_state_path()),
    }
    return merged


def apply() -> None:
    """Apply operator-confirmed listing evidence to the production collector."""
    global _applied, _base_render, _base_collect
    if _applied:
        return

    source_overrides.apply()

    if source_overrides._base_render is not None:
        _base_render = source_overrides._base_render
        source_overrides._base_render = _render_with_feedback

    package = sys.modules.get(__package__)
    if package is not None:
        candidate = getattr(package, "collect_events", None)
        if callable(candidate):
            _base_collect = candidate

            def collect_events(*args, **kwargs):
                return _merge_confirmed_events(
                    dict(_base_collect(*args, **kwargs))
                )

            package.collect_events = collect_events

    _applied = True


__all__ = ["apply"]
