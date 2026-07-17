from __future__ import annotations

import html
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlparse

HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>|<!--.*?-->", re.S)
SUMMARY_HEADING_RE = re.compile(
    r"^(?:about\s+the\s+event|event\s+details?|description)\s*[:\-–—]?\s*",
    re.I,
)
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
    "main", "nav", "ol", "p", "section", "table", "td", "th", "tr", "ul",
}
IGNORED_TAGS = {"script", "style", "noscript", "template"}
TEXT_FIELDS = ("title", "when", "where", "host", "source_name", "summary")
WHERE_ALIASES = ("venue", "place", "where_text", "location", "address")
SUMMARY_ALIASES = ("why_text", "description", "desc")
MAX_ENTITY_DECODE_ROUNDS = 3
OPEN_ENDED_RE = re.compile(r"\b(?:ongoing|permanent|from|since)\b", re.I)
SYNTHETIC_FRAGMENT_RE = re.compile(r"^(?:nhb|nhb-json|structured)-", re.I)
MEDIA_RE = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$", re.I)
GENERIC_LEAF_RE = re.compile(
    r"^(?:whats?-on|whatson|events?|overview|view-all|calendar|programmes?|programs?|"
    r"activities?|exhibitions?|workshops?|tours?|shows?|performances?)$",
    re.I,
)
VERIFIED_POLICY = "canonical-detail-evidence-v1"


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in IGNORED_TAGS:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if name == "li":
            self.parts.append(" • ")
        elif name in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in IGNORED_TAGS:
            if self.ignored_depth:
                self.ignored_depth -= 1
            return
        if not self.ignored_depth and name in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def _collapse(value: object) -> str:
    text = str(value or "").replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def _decode_entities(value: object) -> str:
    decoded = str(value or "")
    for _ in range(MAX_ENTITY_DECODE_ROUNDS):
        next_value = html.unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def plain_text(value: object) -> str:
    raw = _decode_entities(value)
    if not raw:
        return ""
    if not HTML_TAG_RE.search(raw):
        return _collapse(raw)

    parser = _PlainTextParser()
    try:
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    return _collapse(text)


def _clean_summary(value: object) -> str:
    return SUMMARY_HEADING_RE.sub("", plain_text(value)).strip()


def _iso_date(value: object) -> date | None:
    text = _collapse(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _invalid_event(event: dict[str, Any]) -> bool:
    url = _collapse(event.get("url"))
    if not url.startswith(("http://", "https://")):
        return True
    parsed = urlparse(url)
    if parsed.fragment and SYNTHETIC_FRAGMENT_RE.match(parsed.fragment):
        return True
    path = unquote(parsed.path).rstrip("/").lower()
    if not path or MEDIA_RE.search(path):
        return True
    leaf = path.rsplit("/", 1)[-1].removesuffix(".html")
    if not leaf or GENERIC_LEAF_RE.fullmatch(leaf):
        return True
    policy = _collapse(event.get("candidate_policy"))
    return bool(policy and policy != VERIFIED_POLICY)


def _expired_event(event: dict[str, Any]) -> bool:
    when = _collapse(event.get("when"))
    if OPEN_ENDED_RE.search(when):
        return False
    end = _iso_date(event.get("end_date"))
    start = _iso_date(event.get("start_date"))
    effective_end = end or start
    return bool(effective_end and effective_end < date.today())


def normalize_event(event: dict[str, Any]) -> tuple[dict[str, Any], int]:
    normalized = dict(event)
    changed = 0

    for key in TEXT_FIELDS + WHERE_ALIASES + SUMMARY_ALIASES:
        if key not in normalized:
            continue
        original = str(normalized.get(key) or "")
        cleaned = _clean_summary(original) if key == "summary" or key in SUMMARY_ALIASES else plain_text(original)
        if cleaned != original:
            changed += 1
        normalized[key] = cleaned

    if not normalized.get("where"):
        for alias in WHERE_ALIASES:
            candidate = normalized.get(alias)
            if candidate:
                normalized["where"] = candidate
                changed += 1
                break

    if not normalized.get("summary"):
        for alias in SUMMARY_ALIASES:
            candidate = normalized.get(alias)
            if candidate:
                normalized["summary"] = candidate
                changed += 1
                break

    return normalized, changed


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    results = payload.get("results")
    if not isinstance(results, list):
        normalized["text_normalizer"] = "plain-text-v1"
        normalized["normalized_text_fields"] = 0
        normalized["expired_events_removed"] = 0
        normalized["invalid_events_removed"] = 0
        return normalized

    output: list[Any] = []
    changed = 0
    expired_removed = 0
    invalid_removed = 0
    for item in results:
        if isinstance(item, dict):
            clean_item, item_changed = normalize_event(item)
            if _invalid_event(clean_item):
                invalid_removed += 1
                continue
            if _expired_event(clean_item):
                expired_removed += 1
                continue
            output.append(clean_item)
            changed += item_changed
        else:
            output.append(item)

    normalized["results"] = output
    normalized["count"] = len(output)
    normalized["text_normalizer"] = "plain-text-v1"
    normalized["normalized_text_fields"] = changed
    normalized["expired_events_removed"] = expired_removed
    normalized["invalid_events_removed"] = invalid_removed
    return normalized


__all__ = ["normalize_event", "normalize_payload", "plain_text"]
