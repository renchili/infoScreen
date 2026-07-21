from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import extract as _extract
from . import official_feeds as _official_feeds
from . import review_runtime_authority as _review_runtime
from . import source_overrides as _source_overrides

MANDAI_SOURCE_ID = "mandai"
LISTING_REFERENCE_PREFIX = "infoscreen-card-"
LISTING_REFERENCE_RE = re.compile(r"^infoscreen-card-[0-9a-f]{16}$")
_DATE_LABEL_RE = re.compile(r"^date\s*:?\s*(.+)$", re.I)
_TIME_LABEL_RE = re.compile(r"^time\s*:?\s*(.+)$", re.I)
_LOCATION_LABEL_RE = re.compile(r"^(?:location|venue|where)\s*:?\s*(.+)$", re.I)
_OPEN_DATE_RE = re.compile(
    r"^(?:daily|ongoing|selected dates?|weekends?|public holidays?)$",
    re.I,
)

_APPLIED = False
_BASE_LISTING_CARD = None
_BASE_CANDIDATE_URL = None
_BASE_ENRICH = None
_BASE_DOM_EVENT = None
_BASE_DETAIL_CANDIDATE = None
_BASE_DIAGNOSTIC_REASON = None
_BASE_REVIEW_CANONICAL_URL = None

_OLD_NHB_DATE_GATE = "    if (!hasDateText(text)) return false;"
_NEW_NHB_DATE_GATE = r'''    if (!hasDateText(text) && !(
      String(sourceId || "").toLowerCase() === "mandai"
      && /\b(?:date\s*:?\s*)?(?:daily|ongoing|selected dates?|weekends?|public holidays?)\b/i.test(text)
    )) return false;'''

_OLD_NHB_PUSH = '''      const listingDetailUrls = detailUrls(el);
      if (listingDetailUrls.length !== 1) continue;
      const url = listingDetailUrls[0];
      push(out, seen, el, url, "", "nhb_dom_card");'''
_NEW_NHB_PUSH = '''      const listingDetailUrls = detailUrls(el);
      const sourceKey = String(sourceId || "").toLowerCase();
      if (sourceKey === "mandai") {
        if (listingDetailUrls.length > 1) continue;
        const url = listingDetailUrls[0] || document.location.href;
        push(out, seen, el, url, "", "nhb_dom_card");
        continue;
      }
      if (listingDetailUrls.length !== 1) continue;
      const url = listingDetailUrls[0];
      push(out, seen, el, url, "", "nhb_dom_card");'''


def _is_mandai(source: dict[str, Any]) -> bool:
    return _extract.clean(source.get("id")).lower() == MANDAI_SOURCE_ID


def _card_identity(card: dict[str, Any]) -> str:
    existing = _extract.clean(card.get("id"))
    material = "\n".join(
        [
            existing,
            _extract.clean(card.get("text"))[:1000],
            _extract.clean(card.get("page_url")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def listing_reference_url(listing_url: str, card: dict[str, Any]) -> str:
    """Return an honest official-listing URL with a stable local card fragment."""

    parsed = urlsplit(_extract.clean(listing_url))
    fragment = f"{LISTING_REFERENCE_PREFIX}{_card_identity(card)}"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, fragment))


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        lines = [_extract.clean(item) for item in raw if _extract.clean(item)]
        if lines:
            return lines
    return _extract.lines(card.get("text") or "")


def _date_value(line: str) -> str:
    match = _DATE_LABEL_RE.fullmatch(line)
    value = _extract.clean(match.group(1) if match else line)
    if not value:
        return ""
    if _extract.DATE_LINE_RE.search(value):
        return value
    if re.search(r"\b20\d{2}\b", value) and re.search(
        rf"\b(?:{_extract.MONTH_WORD})[a-z]*\b",
        value,
        re.I,
    ):
        return value
    if _OPEN_DATE_RE.fullmatch(value):
        return value
    return ""


def _time_value(line: str) -> str:
    match = _TIME_LABEL_RE.fullmatch(line)
    value = _extract.clean(match.group(1) if match else line)
    if not value or _extract.DATE_LINE_RE.search(value):
        return ""
    if match or _extract.TIME_RE.search(value):
        return value
    return ""


def _mandai_when(card: dict[str, Any]) -> tuple[str, str]:
    date_value = ""
    date_line = ""
    time_value = ""
    for line in _card_lines(card):
        if not date_value:
            candidate = _date_value(line)
            if candidate:
                date_value = candidate
                date_line = line
                continue
        if not time_value:
            candidate = _time_value(line)
            if candidate:
                time_value = candidate
    if not date_value:
        return "", ""
    if time_value and time_value.casefold() not in date_value.casefold():
        return f"{date_value} · {time_value}", date_line
    return date_value, date_line


def _mandai_where(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    date_line: str,
) -> str:
    for line in _card_lines(card):
        match = _LOCATION_LABEL_RE.fullmatch(line)
        if match:
            value = _extract.clean(match.group(1))
            if value:
                return value
    return _extract.pick_venue(source, card, when, date_line)


def _mandai_summary(card: dict[str, Any], title: str, when: str, where: str) -> str:
    title_key = _extract.norm_key(title)
    where_key = _extract.norm_key(where)
    narrative: list[str] = []
    for line in _card_lines(card):
        key = _extract.norm_key(line)
        if not line or key in {title_key, where_key}:
            continue
        if _DATE_LABEL_RE.fullmatch(line) or _TIME_LABEL_RE.fullmatch(line):
            continue
        if _LOCATION_LABEL_RE.fullmatch(line):
            continue
        if _date_value(line) or _time_value(line):
            continue
        if _extract.BAD_LINE_RE.search(line):
            continue
        if len(line) < 35 or len(line) > 700:
            continue
        if _extract.VENUE_RE.search(line) and len(line.split()) <= 10:
            continue
        narrative.append(line)
        if len(narrative) >= 3:
            break
    if narrative:
        return _extract.short(" ".join(narrative), 700)
    return _extract.pick_summary(card, title, when, where)


def _mandai_dom_event(
    source: dict[str, Any],
    card: dict[str, Any],
) -> dict[str, Any] | None:
    title = _extract.pick_title(card)
    when, date_line = _mandai_when(card)
    if not title or not when:
        return None
    where = _mandai_where(source, card, when, date_line)
    summary = _mandai_summary(card, title, when, where)
    dates = _extract.label_dates(when)
    listing_only = int(card.get("detail_url_count") or 0) == 0
    return {
        "title": title,
        "when": when,
        "where": where,
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": _extract.clean(card.get("url")),
        "summary": summary,
        "start_date": _extract.best_start_date(when),
        "end_date": max(dates).isoformat() if len(dates) >= 2 else "",
        "kind": "event",
        "source_type": (
            "official_listing_card_without_detail"
            if listing_only
            else "official_listing_card"
        ),
        "listing_only": listing_only,
        "detail_available": not listing_only,
        "debug_screenshot": card.get("screenshot") or "",
        "debug_detail_url_count": int(card.get("detail_url_count") or 0),
    }


def _listing_card(
    source: dict[str, Any],
    card: dict[str, Any],
    listing_url: str,
) -> dict[str, Any] | None:
    admitted = _BASE_LISTING_CARD(source, card, listing_url)
    if admitted is not None or not _is_mandai(source):
        return admitted
    if _extract.clean(card.get("extraction_mode")) != "nhb_dom_card":
        return None
    if int(card.get("detail_url_count") or 0) != 0:
        return None
    if _mandai_dom_event(source, card) is None:
        return None

    reference = listing_reference_url(listing_url, card)
    admitted = dict(card)
    admitted.update(
        url=reference,
        page_url=_extract.clean(listing_url),
        listing_evidence=_source_overrides.LISTING_EVIDENCE,
        listing_url=_extract.clean(listing_url),
        listing_card_id=_extract.clean(card.get("id")) or _card_identity(card),
        listing_extraction_mode="mandai_listing_card_without_detail",
        listing_only=True,
        detail_available=False,
    )
    return admitted


def _candidate_url(source: dict[str, Any], card: dict[str, Any]) -> str:
    if _is_mandai(source) and card.get("listing_only") is True:
        return _extract.clean(card.get("url"))
    return _BASE_CANDIDATE_URL(source, card)


def _enrich(
    source: dict[str, Any],
    cards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not _is_mandai(source):
        return _BASE_ENRICH(source, cards)

    enrichable = [card for card in cards if card.get("listing_only") is not True]
    enriched, debug = _BASE_ENRICH(source, enrichable)
    iterator = iter(enriched)
    output = [card if card.get("listing_only") is True else next(iterator) for card in cards]
    debug = dict(debug)
    debug["candidates"] = len(cards)
    debug["listing_only"] = len(cards) - len(enrichable)
    return output, debug


def _dom_event(source: dict[str, Any], card: dict[str, Any]) -> dict[str, Any] | None:
    if _is_mandai(source):
        return _mandai_dom_event(source, card)
    return _BASE_DOM_EVENT(source, card)


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    if _is_mandai(source) and card.get("listing_only") is True:
        event, reason = _extract.event_from_card(source, card)
        if event is None:
            return {
                "detail_url": raw_url,
                "title": _extract.pick_title(card),
                "when": "",
                "where": "",
                "summary": _extract.clean(card.get("text"))[:500],
                "detail_status": "incomplete",
                "detail_error": reason,
                "detail_page_title": "",
            }
        return {
            "detail_url": raw_url,
            "title": str(event.get("title") or _extract.pick_title(card)),
            "when": str(event.get("when") or ""),
            "where": str(event.get("where") or ""),
            "summary": str(event.get("summary") or ""),
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": "",
        }
    return _BASE_DETAIL_CANDIDATE(context, source, listing_url, raw_url, card)


def _diagnostic_reason(diagnostic):
    if diagnostic.candidates_created > 0 and diagnostic.detail_link_count == 0:
        return (
            "collected",
            "events_recognised_from_complete_listing_cards",
            f"Recognised {diagnostic.candidates_created} Event candidate(s) directly "
            "from complete official listing cards without detail pages.",
        )
    return _BASE_DIAGNOSTIC_REASON(diagnostic)


def _review_canonical_url(value: object) -> str:
    canonical = _BASE_REVIEW_CANONICAL_URL(value)
    raw_fragment = urlsplit(str(value or "").strip()).fragment
    if not LISTING_REFERENCE_RE.fullmatch(raw_fragment):
        return canonical
    parsed = urlsplit(canonical)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, raw_fragment)
    )


def _patch_browser() -> None:
    script = _browser.CARD_JS
    if _OLD_NHB_DATE_GATE in script:
        script = script.replace(_OLD_NHB_DATE_GATE, _NEW_NHB_DATE_GATE, 1)
    elif _NEW_NHB_DATE_GATE not in script:
        raise RuntimeError("mandai_nhb_date_gate_missing")

    if _OLD_NHB_PUSH in script:
        script = script.replace(_OLD_NHB_PUSH, _NEW_NHB_PUSH, 1)
    elif _NEW_NHB_PUSH not in script:
        raise RuntimeError("mandai_nhb_card_push_missing")
    _browser.CARD_JS = script


def apply() -> None:
    """Install complete-card authority for Mandai cards without detail pages."""

    global _APPLIED
    global _BASE_LISTING_CARD, _BASE_CANDIDATE_URL, _BASE_ENRICH, _BASE_DOM_EVENT
    global _BASE_DETAIL_CANDIDATE, _BASE_DIAGNOSTIC_REASON
    global _BASE_REVIEW_CANONICAL_URL
    if _APPLIED:
        return

    _source_overrides.apply()
    _BASE_LISTING_CARD = _source_overrides._listing_card
    _BASE_CANDIDATE_URL = _source_overrides._candidate_url
    _BASE_ENRICH = _source_overrides._enrich
    _BASE_DOM_EVENT = _source_overrides._dom_event
    _BASE_DETAIL_CANDIDATE = _review._detail_candidate
    _BASE_DIAGNOSTIC_REASON = _diagnostics._reason
    _BASE_REVIEW_CANONICAL_URL = _review_runtime._canonical_url

    _patch_browser()
    _source_overrides._listing_card = _listing_card
    _source_overrides._candidate_url = _candidate_url
    _source_overrides._enrich = _enrich
    _source_overrides._dom_event = _dom_event
    _review._detail_candidate = _detail_candidate
    _diagnostics._reason = _diagnostic_reason
    _review_runtime._canonical_url = _review_canonical_url
    _APPLIED = True


__all__ = [
    "apply",
    "listing_reference_url",
    "LISTING_REFERENCE_RE",
    "MANDAI_SOURCE_ID",
]
