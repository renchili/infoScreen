from __future__ import annotations

import hashlib
import re
from typing import Any

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds
from . import source_overrides as _source_overrides

MANDAI_SOURCE_ID = "mandai"
_DATE_LABEL_RE = re.compile(r"^date\s*:?\s*(.*)$", re.I)
_TIME_LABEL_RE = re.compile(r"^time\s*:?\s*(.*)$", re.I)
_LOCATION_LABEL_RE = re.compile(r"^(?:location|venue|where)\s*:?\s*(.*)$", re.I)
_OPEN_DATE_RE = re.compile(
    r"^(?:daily|ongoing|permanent|selected dates?|weekends?|public holidays?)$",
    re.I,
)

_APPLIED = False
_BASE_LISTING_CARD = None
_BASE_CANDIDATE_URL = None
_BASE_ENRICH = None
_BASE_DOM_EVENT = None
_BASE_SAME_CANDIDATE = None
_BASE_MERGE_STRUCTURED = None

_OLD_NHB_DATE_GATE = "    if (!hasDateText(text)) return false;"
_NEW_NHB_DATE_GATE = r'''    if (!hasDateText(text) && !(
      String(sourceId || "").toLowerCase() === "mandai"
      && /\b(?:date\s*:?\s*)?(?:daily|ongoing|permanent|selected dates?|weekends?|public holidays?)\b/i.test(text)
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


class OfficialListingCardURL(str):
    """A real official URL whose in-memory identity also includes one DOM card.

    Python's collector historically deduplicates on the ``url`` object before it
    knows a card's title/date. Multiple Mandai activities legitimately share the
    same official listing URL. This str subclass serializes as that exact URL but
    keeps separate cards distinct while the collector's sets are built.
    """

    def __new__(cls, value: str, identity: str):
        instance = super().__new__(cls, value)
        instance.card_identity = identity
        return instance

    def __hash__(self) -> int:
        return hash((str(self), self.card_identity))

    def __eq__(self, other: object) -> bool:
        return bool(
            isinstance(other, OfficialListingCardURL)
            and str(self) == str(other)
            and self.card_identity == other.card_identity
        )


def is_mandai(source: dict[str, Any]) -> bool:
    return _extract.clean(source.get("id")).lower() == MANDAI_SOURCE_ID


def card_identity(card: dict[str, Any]) -> str:
    """Return a stable identity from the rendered listing card, not its URL."""

    material = "\n".join(
        [
            _extract.clean(card.get("id")),
            _extract.clean(card.get("text"))[:1200],
            _extract.clean(card.get("page_url")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        lines = [_extract.clean(item) for item in raw if _extract.clean(item)]
        if lines:
            return lines
    return _extract.lines(card.get("text") or "")


def _labeled_value(
    lines: list[str],
    pattern: re.Pattern[str],
    index: int,
) -> tuple[str, int]:
    match = pattern.fullmatch(lines[index])
    if not match:
        return "", index
    inline = _extract.clean(match.group(1))
    if inline:
        return inline, index
    for next_index in range(index + 1, min(len(lines), index + 4)):
        candidate = _extract.clean(lines[next_index])
        if not candidate:
            continue
        if any(
            other.fullmatch(candidate)
            for other in (_DATE_LABEL_RE, _TIME_LABEL_RE, _LOCATION_LABEL_RE)
        ):
            break
        return candidate, next_index
    return "", index


def _date_value(line: str) -> str:
    value = _extract.clean(line)
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
    return value if _OPEN_DATE_RE.fullmatch(value) else ""


def _time_value(line: str) -> str:
    value = _extract.clean(line)
    if not value or _extract.DATE_LINE_RE.search(value):
        return ""
    return value if _extract.TIME_RE.search(value) else ""


def mandai_when(card: dict[str, Any]) -> tuple[str, str]:
    lines = _card_lines(card)
    date_value = ""
    date_line = ""
    time_value = ""

    for index, line in enumerate(lines):
        if not date_value:
            labeled, _ = _labeled_value(lines, _DATE_LABEL_RE, index)
            candidate = _date_value(labeled or line)
            if candidate:
                date_value = candidate
                date_line = line
                continue
        if not time_value:
            labeled, _ = _labeled_value(lines, _TIME_LABEL_RE, index)
            candidate = _time_value(labeled or line)
            if candidate:
                time_value = candidate

    if not date_value:
        return "", ""
    if time_value and time_value.casefold() not in date_value.casefold():
        return f"{date_value} · {time_value}", date_line
    return date_value, date_line


def mandai_where(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    date_line: str,
) -> str:
    lines = _card_lines(card)
    for index in range(len(lines)):
        value, _ = _labeled_value(lines, _LOCATION_LABEL_RE, index)
        if value:
            return value
    return _extract.pick_venue(source, card, when, date_line)


def mandai_summary(card: dict[str, Any], title: str, when: str, where: str) -> str:
    title_key = _extract.norm_key(title)
    where_key = _extract.norm_key(where)
    narrative: list[str] = []
    for line in _card_lines(card):
        key = _extract.norm_key(line)
        if not line or key in {title_key, where_key}:
            continue
        if any(
            pattern.fullmatch(line)
            for pattern in (_DATE_LABEL_RE, _TIME_LABEL_RE, _LOCATION_LABEL_RE)
        ):
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


def mandai_event(
    source: dict[str, Any],
    card: dict[str, Any],
) -> dict[str, Any] | None:
    title = _extract.pick_title(card)
    when, date_line = mandai_when(card)
    if not title or not when:
        return None
    where = mandai_where(source, card, when, date_line)
    summary = mandai_summary(card, title, when, where)
    dates = _extract.label_dates(when)
    listing_only = int(card.get("detail_url_count") or 0) == 0
    return {
        "title": title,
        "when": when,
        "where": where,
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": card.get("url") or "",
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


def review_detail(
    source: dict[str, Any],
    listing_url: str,
    card: dict[str, Any],
) -> dict[str, Any]:
    """Build a Review candidate from a complete card without opening a page."""

    event = mandai_event(source, card)
    if event is None:
        return {
            "detail_url": listing_url,
            "title": _extract.pick_title(card),
            "when": "",
            "where": "",
            "summary": _extract.clean(card.get("text"))[:500],
            "detail_status": "incomplete",
            "detail_error": "listing_card_fields_incomplete",
            "detail_page_title": "",
        }
    return {
        "detail_url": listing_url,
        "title": event["title"],
        "when": event["when"],
        "where": event["where"],
        "summary": event["summary"],
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "",
    }


def _listing_card(
    source: dict[str, Any],
    card: dict[str, Any],
    listing_url: str,
) -> dict[str, Any] | None:
    admitted = _BASE_LISTING_CARD(source, card, listing_url)
    if admitted is not None or not is_mandai(source):
        return admitted
    if _extract.clean(card.get("extraction_mode")) != "nhb_dom_card":
        return None
    if int(card.get("detail_url_count") or 0) != 0:
        return None
    if mandai_event(source, card) is None:
        return None

    identity = _extract.clean(card.get("id")) or card_identity(card)
    official_url = _extract.clean(listing_url)
    admitted = dict(card)
    admitted.update(
        url=OfficialListingCardURL(official_url, identity),
        page_url=official_url,
        listing_evidence=_source_overrides.LISTING_EVIDENCE,
        listing_url=official_url,
        listing_card_id=identity,
        listing_extraction_mode="mandai_listing_card_without_detail",
        listing_only=True,
        detail_available=False,
    )
    return admitted


def _candidate_url(source: dict[str, Any], card: dict[str, Any]):
    if is_mandai(source) and card.get("listing_only") is True:
        return card.get("url") or card.get("listing_url") or ""
    return _BASE_CANDIDATE_URL(source, card)


def _same_candidate(
    structured: dict[str, Any],
    listing: dict[str, Any],
) -> bool:
    if listing.get("listing_only") is True:
        structured_title = _official_feeds.card_title(structured)
        listing_title = _official_feeds.card_title(listing)
        return bool(structured_title and structured_title == listing_title)
    return _BASE_SAME_CANDIDATE(structured, listing)


def _merge_structured_with_listing(
    structured: dict[str, Any],
    listing: dict[str, Any],
) -> dict[str, Any]:
    if listing.get("listing_only") is not True:
        return _BASE_MERGE_STRUCTURED(structured, listing)

    merged = dict(listing)
    structured_event = structured.get("structured_event")
    if isinstance(structured_event, dict):
        event = dict(structured_event)
        event["url"] = str(listing.get("listing_url") or listing.get("url") or "")
        merged["structured_event"] = event
    merged.update(
        detail_url_count=0,
        detail_urls=[],
        listing_only=True,
        detail_available=False,
    )
    return merged


def _enrich(
    source: dict[str, Any],
    cards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not is_mandai(source):
        return _BASE_ENRICH(source, cards)

    enrichable = [card for card in cards if card.get("listing_only") is not True]
    enriched, debug = _BASE_ENRICH(source, enrichable)
    iterator = iter(enriched)
    output = [
        card if card.get("listing_only") is True else next(iterator)
        for card in cards
    ]
    debug = dict(debug)
    debug["candidates"] = len(cards)
    debug["listing_only"] = len(cards) - len(enrichable)
    return output, debug


def _dom_event(source: dict[str, Any], card: dict[str, Any]) -> dict[str, Any] | None:
    if is_mandai(source):
        return mandai_event(source, card)
    return _BASE_DOM_EVENT(source, card)


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
    global _BASE_SAME_CANDIDATE, _BASE_MERGE_STRUCTURED
    if _APPLIED:
        return

    _source_overrides.apply()
    _BASE_LISTING_CARD = _source_overrides._listing_card
    _BASE_CANDIDATE_URL = _source_overrides._candidate_url
    _BASE_ENRICH = _source_overrides._enrich
    _BASE_DOM_EVENT = _source_overrides._dom_event
    _BASE_SAME_CANDIDATE = _source_overrides._same_candidate
    _BASE_MERGE_STRUCTURED = _source_overrides._merge_structured_with_listing

    _patch_browser()
    _source_overrides._listing_card = _listing_card
    _source_overrides._candidate_url = _candidate_url
    _source_overrides._same_candidate = _same_candidate
    _source_overrides._merge_structured_with_listing = _merge_structured_with_listing
    _source_overrides._enrich = _enrich
    _source_overrides._dom_event = _dom_event
    _APPLIED = True


__all__ = [
    "apply",
    "card_identity",
    "is_mandai",
    "mandai_event",
    "OfficialListingCardURL",
    "review_detail",
]
