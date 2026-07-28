from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from . import event_review as _review
from . import event_review_diagnostics as _diagnostics

_APPLIED = False
_BASE_COLLECT = None
HTTP_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 8_000_000
MAX_PREVIEW_EVENTS = 40

_DATE_RE = re.compile(
    r"\b20\d{2}\b|"
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b|"
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2}\b|"
    r"\b(?:daily|ongoing|permanent|today|tomorrow)\b",
    re.I,
)
_MEDIA_RE = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|zip)$", re.I)
_GENERIC_LINK_RE = re.compile(r"^(?:view|view details?|details?|learn more|read more|find out more|book now|buy tickets?)$", re.I)
_EXPLICIT_CARD_RE = re.compile(r"(?:^|[-_\s])(card|tile|event|programme|program|exhibition|listing|result|item)(?:$|[-_\s])", re.I)
_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "p", "section", "table", "td",
    "th", "tr", "ul",
}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _Node:
    __slots__ = ("tag", "attrs", "parent", "children", "data")

    def __init__(self, tag: str, attrs: dict[str, str], parent: _Node | None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[_Node] = []
        self.data: list[str] = []


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {}, None)
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {str(key).lower(): str(value or "") for key, value in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if node.tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower() and tag.lower() not in _VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].data.append(data)


def _walk(node: _Node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _inside(node: _Node, ancestor: _Node) -> bool:
    current: _Node | None = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _raw_text(node: _Node) -> str:
    parts: list[str] = []

    def visit(current: _Node) -> None:
        if current.tag in _BLOCK_TAGS:
            parts.append("\n")
        parts.extend(current.data)
        for child in current.children:
            visit(child)
        if current.tag in _BLOCK_TAGS:
            parts.append("\n")

    visit(node)
    return "".join(parts)


def _lines(node: _Node) -> list[str]:
    values = [re.sub(r"\s+", " ", value).strip() for value in _raw_text(node).splitlines()]
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _first(root: _Node, predicate) -> _Node | None:
    return next((node for node in _walk(root) if predicate(node)), None)


def _host_allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in source.get("allowed_domains") or []
        )
    )


def _is_mbs_preview(store: _review.EventReviewStore) -> bool:
    if not store.root.name.startswith("infoscreen-event-preview-"):
        return False
    state = store.load()
    confirmed = [item for item in state.listing_pages if item.decision == "confirmed"]
    return bool(
        len(confirmed) == 1
        and (urlsplit(confirmed[0].url).hostname or "").lower().endswith("marinabaysands.com")
    )


def _fetch_html(url: str, source: dict[str, Any]) -> tuple[str, int, str]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-SG,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        final_url = str(response.geturl())
        if not _host_allowed(final_url, source):
            raise ValueError("preview HTTP redirect left the source allow-list")
        status = int(getattr(response, "status", 200) or 200)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("preview HTML exceeds the 8 MB limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return final_url, status, raw.decode(charset, "replace")


def _detail_url(raw: str, base_url: str, listing_url: str, source: dict[str, Any]) -> str:
    value = urljoin(base_url, str(raw or "").strip())
    if not value.startswith(("http://", "https://")) or not _host_allowed(value, source):
        return ""
    parsed = urlsplit(value)
    listing = urlsplit(listing_url)
    path = parsed.path.rstrip("/").lower()
    listing_path = listing.path.rstrip("/").lower()
    if not path or path == listing_path or _MEDIA_RE.search(path):
        return ""
    return value.split("#", 1)[0]


def _card_for(anchor: _Node, root: _Node) -> _Node | None:
    current: _Node | None = anchor
    fallback: _Node | None = None
    for _ in range(7):
        if current is None or not _inside(current, root):
            break
        lines = _lines(current)
        text = " ".join(lines)
        if 12 <= len(text) <= 3000 and any(_DATE_RE.search(line) for line in lines):
            classes = current.attrs.get("class", "")
            if current.tag in {"article", "li"} or _EXPLICIT_CARD_RE.search(classes):
                return current
            fallback = fallback or current
        if current is root:
            break
        current = current.parent
    return fallback


def _title(card: _Node, anchor: _Node) -> str:
    heading = _first(card, lambda node: node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"})
    candidates = []
    if heading is not None:
        candidates.extend(_lines(heading))
    candidates.extend(_lines(anchor))
    candidates.extend(_lines(card))
    for value in candidates:
        if not value or len(value) > 240 or _DATE_RE.fullmatch(value) or _GENERIC_LINK_RE.fullmatch(value):
            continue
        return value
    return ""


def extract_preview_rows(html: str, final_url: str, listing_url: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    parser = _TreeParser()
    parser.feed(html)
    root = _first(parser.root, lambda node: node.tag == "main" or node.attrs.get("role", "").lower() == "main")
    root = root or _first(parser.root, lambda node: node.tag == "body") or parser.root

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in _walk(root):
        if anchor.tag != "a" or "href" not in anchor.attrs:
            continue
        detail_url = _detail_url(anchor.attrs.get("href", ""), final_url, listing_url, source)
        if not detail_url or detail_url in seen:
            continue
        card = _card_for(anchor, root)
        if card is None:
            continue
        lines = _lines(card)[:80]
        when = next((line for line in lines if len(line) <= 180 and _DATE_RE.search(line)), "")
        title = _title(card, anchor)
        if not title or not when:
            continue
        summary = next(
            (line for line in lines if line not in {title, when} and 24 <= len(line) <= 500 and not _GENERIC_LINK_RE.fullmatch(line)),
            "",
        )
        rows.append(
            {
                "title": title,
                "when": when,
                "where": "",
                "summary": summary,
                "detail_url": detail_url,
                "text": "\n".join(lines),
            }
        )
        seen.add(detail_url)
        if len(rows) >= MAX_PREVIEW_EVENTS:
            break
    return rows


def _collect_http_preview(store: _review.EventReviewStore) -> _review.ReviewState:
    state = store.load()
    confirmed = [item for item in state.listing_pages if item.decision == "confirmed"]
    if len(confirmed) != 1:
        raise ValueError("preview requires exactly one selected listing page")
    listing = confirmed[0]
    source = store.source(listing.source_id)
    if not _host_allowed(listing.url, source):
        raise ValueError("listing page is outside the source allow-list")

    started = _review.utc_now()
    final_url, http_status, html = _fetch_html(listing.url, source)
    if http_status >= 400:
        raise ValueError(f"listing_http_status_{http_status}")
    rows = extract_preview_rows(html, final_url, listing.url, source)
    if not rows:
        raise ValueError("MBS HTML loaded but no activity cards were recognised")

    default_venue = str(source.get("default_venue") or source.get("name") or "")
    candidates: list[_review.EventCandidate] = []
    for index, raw in enumerate(rows):
        detail_url = str(raw.get("detail_url") or "")
        candidates.append(
            _review.EventCandidate(
                candidate_id=_review.stable_id(listing.source_id, listing.url, detail_url),
                source_id=listing.source_id,
                source_name=listing.source_name,
                listing_url=listing.url,
                detail_url=detail_url,
                title=str(raw.get("title") or "")[:300],
                when=str(raw.get("when") or "")[:180],
                where=str(raw.get("where") or default_venue)[:300],
                summary=str(raw.get("summary") or "")[:500],
                detail_status="incomplete",
                detail_error="preview_http_listing_evidence_only",
                detail_page_title="",
                evidence=_review.EventEvidence(
                    selector=f"http-preview:{index}",
                    selector_index=index,
                    selector_match_count=len(rows),
                    document_position={"x": 0, "y": 0, "width": 0, "height": 0},
                    viewport_position={"x": 0, "y": 0, "width": 0, "height": 0},
                    page_index=0,
                    page_url=final_url,
                    text=str(raw.get("text") or "")[:3000],
                ),
                collected_at=started,
            )
        )

    return store.replace_events(
        candidates,
        {
            "started_at": started,
            "completed_at": _review.utc_now(),
            "confirmed_listing_count": 1,
            "candidate_count": len(candidates),
            "preview_mode": "http_server_rendered_html",
            "formal_collector_bypassed": True,
            "chromium_bypassed": True,
            "selector_audit_skipped": True,
            "listing_diagnostics_skipped": True,
            "detail_page_requests_skipped": len(candidates),
            "final_url": final_url,
            "http_status": http_status,
            "errors": [],
        },
    )


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    if _is_mbs_preview(store):
        return _collect_http_preview(store)
    return _BASE_COLLECT(store)


def apply() -> None:
    global _APPLIED, _BASE_COLLECT
    if _APPLIED:
        _diagnostics.collect_event_candidates = collect_event_candidates
        return
    _BASE_COLLECT = _diagnostics.collect_event_candidates
    _diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = ["HTTP_TIMEOUT_SECONDS", "apply", "collect_event_candidates", "extract_preview_rows"]
