from __future__ import annotations

import re
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse

from . import extract as _extract

WHERE_INLINE_RE = re.compile(r"^(?:where|location|venue)\s*:\s*(.+)$", re.I)
WHERE_LABEL_RE = re.compile(r"^(?:where|location|venue)\s*:?\s*$", re.I)
OTHER_FIELD_LABEL_RE = re.compile(
    r"^(?:when|date|time|suitable for|ticket information|ticketing(?:\s*/\s*admission)?|admission)\s*:?\s*$",
    re.I,
)
VENUE_NOISE_RE = re.compile(
    r"^(?:get directions|see ticketing.*|open the official page.*|book now|buy tickets?)$",
    re.I,
)
NARRATIVE_VENUE_RE = re.compile(
    r"\b(?:presents?|explore|discover|celebrates?|considers?|invites?|journey|"
    r"exhibition|performance|co-curated|newly revamped|find out|learn more)\b",
    re.I,
)

_applied = False
_base_event_from_card = None


def public_detail_url(source: dict[str, Any], value: object) -> str:
    """Map an official CMS detail URL to the source's public detail route."""
    url = _extract.clean(value)
    if not url.startswith(("http://", "https://")):
        return url

    parsed = urlparse(url)
    path = parsed.path
    for raw_rule in source.get("public_detail_url_rewrites") or []:
        if not isinstance(raw_rule, dict):
            continue
        source_prefix = str(raw_rule.get("from") or "").rstrip("/")
        target_prefix = str(raw_rule.get("to") or "").rstrip("/")
        if not source_prefix:
            continue
        if path != source_prefix and not path.startswith(source_prefix + "/"):
            continue
        suffix = path[len(source_prefix):]
        rewritten = f"{target_prefix}{suffix}" or "/"
        if not rewritten.startswith("/"):
            rewritten = "/" + rewritten
        parsed = parsed._replace(path=rewritten, fragment="")
        return urlunparse(parsed)

    return urlunparse(parsed._replace(fragment=""))


def _valid_venue(value: object) -> str:
    venue = _extract.clean(value)
    if not venue or len(venue) > 140 or len(venue.split()) > 16:
        return ""
    if WHERE_LABEL_RE.fullmatch(venue) or OTHER_FIELD_LABEL_RE.fullmatch(venue):
        return ""
    if VENUE_NOISE_RE.search(venue) or NARRATIVE_VENUE_RE.search(venue):
        return ""
    if _extract.DATE_LINE_RE.search(venue) or _extract.TIME_RE.search(venue):
        return ""
    return venue


def detail_labeled_venue(card: dict[str, Any]) -> str:
    """Read a venue paired with an explicit Where/Location/Venue label."""
    raw_lines = card.get("text_lines")
    if isinstance(raw_lines, list):
        lines = [_extract.clean(item) for item in raw_lines if _extract.clean(item)]
    else:
        lines = _extract.lines(card.get("text") or "")

    for index, line in enumerate(lines):
        inline = WHERE_INLINE_RE.fullmatch(line)
        if inline:
            venue = _valid_venue(inline.group(1))
            if venue:
                return venue
            continue
        if not WHERE_LABEL_RE.fullmatch(line):
            continue
        for candidate in lines[index + 1:index + 4]:
            if WHERE_LABEL_RE.fullmatch(candidate) or OTHER_FIELD_LABEL_RE.fullmatch(candidate):
                break
            venue = _valid_venue(candidate)
            if venue:
                return venue
    return ""


def _normalise_card_urls(source: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    normalised = dict(card)
    for key in ("url", "page_url"):
        if normalised.get(key):
            normalised[key] = public_detail_url(source, normalised[key])

    urls = normalised.get("detail_urls")
    if isinstance(urls, list):
        normalised["detail_urls"] = [public_detail_url(source, item) for item in urls]

    structured = normalised.get("structured_event")
    if isinstance(structured, dict):
        structured = dict(structured)
        if structured.get("url"):
            structured["url"] = public_detail_url(source, structured["url"])
        normalised["structured_event"] = structured

    evidence = normalised.get("detail_evidence")
    if isinstance(evidence, dict):
        evidence = dict(evidence)
        if evidence.get("canonical_url"):
            evidence["canonical_url"] = public_detail_url(source, evidence["canonical_url"])
        normalised["detail_evidence"] = evidence
    return normalised


def event_from_card(source: dict[str, Any], card: dict[str, Any]):
    normalised_card = _normalise_card_urls(source, card)
    event, reason = _base_event_from_card(source, normalised_card)
    if not event:
        return event, reason

    repaired = dict(event)
    repaired["url"] = public_detail_url(source, repaired.get("url") or normalised_card.get("url"))
    venue = detail_labeled_venue(normalised_card)
    if venue:
        repaired["where"] = venue
        repaired["venue_authority"] = "official_detail_label"
    return repaired, reason


def apply() -> None:
    global _applied, _base_event_from_card
    if _applied:
        return
    _base_event_from_card = _extract.event_from_card
    _extract.event_from_card = event_from_card
    package = sys.modules.get(__package__)
    if package is not None:
        package.event_from_card = event_from_card
    _applied = True


__all__ = ["apply", "detail_labeled_venue", "event_from_card", "public_detail_url"]
