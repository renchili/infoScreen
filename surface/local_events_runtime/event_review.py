from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .browser import CARD_JS, LOAD_MORE_ROUNDS, NAV_TIMEOUT_MS, PREPARE_PAGE_JS, launch_chromium

SURFACE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SURFACE_DIR / "conf" / "event_sources.json"
DEFAULT_REVIEW_ROOT = SURFACE_DIR / ".env" / "local_event_review"

LISTING_DISCOVERY_JS = r"""
(args) => {
  const allowed = (args.allowedDomains || []).map(value => String(value).replace(/^www\./, "").toLowerCase());
  const terms = /\b(event|events|what'?s on|whats-on|whatson|programme|programmes|program|programs|activities|activity|happenings|exhibition|exhibitions|calendar)\b/i;
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const sameDomain = raw => {
    try {
      const host = new URL(raw, location.href).hostname.replace(/^www\./, "").toLowerCase();
      return allowed.some(domain => host === domain || host.endsWith("." + domain));
    } catch {
      return false;
    }
  };
  const rows = [];
  const seen = new Set();
  for (const anchor of document.querySelectorAll("a[href]")) {
    const href = new URL(anchor.getAttribute("href"), location.href).href;
    const text = clean([anchor.innerText, anchor.textContent, anchor.getAttribute("aria-label"), anchor.getAttribute("title")].join(" "));
    if (!sameDomain(href) || !terms.test(text + " " + href)) continue;
    const url = new URL(href);
    url.hash = "";
    const key = url.href;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({url: key, link_text: text.slice(0, 240), page_url: location.href});
    if (rows.length >= 80) break;
  }
  return rows;
}
"""

CARD_EVIDENCE_JS = r"""
() => {
  const stable = value => /^[A-Za-z_][A-Za-z0-9_-]{0,80}$/.test(String(value || ""));
  const esc = value => window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/[^A-Za-z0-9_-]/g, char => "\\" + char);
  const part = element => {
    if (stable(element.id)) return "#" + esc(element.id);
    let value = element.tagName.toLowerCase();
    for (const name of ["data-testid", "data-test", "data-component", "data-module"]) {
      const attribute = element.getAttribute(name);
      if (attribute && /^[A-Za-z0-9_.:-]{1,120}$/.test(attribute)) return `${value}[${name}="${attribute}"]`;
    }
    const classes = [...element.classList].filter(stable).filter(name => !/^(active|selected|open|hover|focus|visible|hidden)$/i.test(name)).slice(0, 3);
    if (classes.length) value += "." + classes.map(esc).join(".");
    return value;
  };
  const selectorFor = element => {
    if (stable(element.id)) return "#" + esc(element.id);
    const pieces = [];
    let current = element;
    for (let depth = 0; current && current !== document.body && depth < 8; depth += 1, current = current.parentElement) {
      pieces.unshift(part(current));
      const selector = pieces.join(" > ");
      try {
        const count = document.querySelectorAll(selector).length;
        if (count > 0 && count <= 80) return selector;
      } catch {}
    }
    return pieces.join(" > ");
  };
  const result = {};
  for (const element of document.querySelectorAll("[data-infoscreen-card-id]")) {
    const id = element.getAttribute("data-infoscreen-card-id");
    const selector = selectorFor(element);
    let index = 0;
    let count = 1;
    try {
      const matches = [...document.querySelectorAll(selector)];
      index = Math.max(0, matches.indexOf(element));
      count = matches.length;
    } catch {}
    const rect = element.getBoundingClientRect();
    result[id] = {
      selector,
      selector_index: index,
      selector_match_count: count,
      document_position: {
        x: Math.round(rect.x + window.scrollX),
        y: Math.round(rect.y + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      },
      viewport_position: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    };
  }
  return result;
}
"""

Decision = Literal["pending", "confirmed", "rejected"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_url(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be absolute HTTP or HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain user information")
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def stable_id(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


class ListingPageCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_id: str
    source_name: str
    url: str
    origin: Literal["configured", "discovered"]
    link_text: str = ""
    decision: Decision = "pending"
    discovered_at: str
    reviewed_at: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        return canonical_url(value)


class EventEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str
    selector_index: int = Field(ge=0)
    selector_match_count: int = Field(ge=1)
    document_position: dict[str, int]
    viewport_position: dict[str, int]
    page_index: int = Field(ge=0)
    page_url: str
    text: str


class EventCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_id: str
    source_name: str
    listing_url: str
    detail_url: str
    title: str
    evidence: EventEvidence
    decision: Decision = "pending"
    collected_at: str
    reviewed_at: str | None = None


class EventFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    source_id: str
    source_name: str
    listing_url: str
    page_url: str
    selector: str
    selector_index: int = Field(ge=0)
    selector_match_count: int = Field(ge=1)
    document_position: dict[str, int]
    text: str
    href: str = ""
    created_at: str


class ReviewState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    listing_pages: list[ListingPageCandidate] = Field(default_factory=list)
    events: list[EventCandidate] = Field(default_factory=list)
    feedback: list[EventFeedback] = Field(default_factory=list)
    listing_collection: dict[str, Any] = Field(default_factory=dict)
    event_collection: dict[str, Any] = Field(default_factory=dict)


class EventReviewStore:
    """Persist listing review, event review, and operator feedback as separate local state."""

    def __init__(
        self,
        root: Path | str = DEFAULT_REVIEW_ROOT,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.config_path = Path(config_path).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise RuntimeError("review root must not be a symlink")

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def inventory(self) -> list[dict[str, Any]]:
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        rows = payload.get("sources") or []
        if not isinstance(rows, list):
            raise ValueError("event_sources.json sources must be a list")
        return [dict(row) for row in rows if isinstance(row, dict)]

    def source(self, source_id: str) -> dict[str, Any]:
        for source in self.inventory():
            if str(source.get("id")) == source_id:
                return source
        raise ValueError(f"unknown source_id: {source_id}")

    def load(self) -> ReviewState:
        try:
            return ReviewState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ReviewState()
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"invalid review state: {exc}") from exc

    def save(self, state: ReviewState) -> ReviewState:
        temporary = self.root / f".state.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(
            state.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)
        return state

    def state_payload(self) -> dict[str, Any]:
        state = self.load()
        return {
            "ok": True,
            "sources": [
                {
                    "source_id": str(source.get("id") or ""),
                    "source_name": str(source.get("name") or source.get("id") or ""),
                    "official_home": str(source.get("official_home") or ""),
                }
                for source in self.inventory()
            ],
            **state.model_dump(mode="json"),
        }

    def replace_listing_pages(
        self,
        candidates: list[ListingPageCandidate],
        collection: dict[str, Any],
    ) -> ReviewState:
        state = self.load()
        old = {item.candidate_id: item for item in state.listing_pages}
        merged = []
        for candidate in candidates:
            previous = old.get(candidate.candidate_id)
            if previous is not None:
                candidate.decision = previous.decision
                candidate.reviewed_at = previous.reviewed_at
            merged.append(candidate)
        state.listing_pages = sorted(merged, key=lambda item: (item.source_name.casefold(), item.url))
        state.listing_collection = collection
        return self.save(state)

    def set_listing_decision(self, candidate_id: str, decision: Decision) -> ReviewState:
        state = self.load()
        match = next((item for item in state.listing_pages if item.candidate_id == candidate_id), None)
        if match is None:
            raise ValueError("listing candidate not found")
        match.decision = decision
        match.reviewed_at = utc_now()
        return self.save(state)

    def replace_events(
        self,
        candidates: list[EventCandidate],
        collection: dict[str, Any],
    ) -> ReviewState:
        state = self.load()
        old = {item.candidate_id: item for item in state.events}
        merged = []
        for candidate in candidates:
            previous = old.get(candidate.candidate_id)
            if previous is not None:
                candidate.decision = previous.decision
                candidate.reviewed_at = previous.reviewed_at
            merged.append(candidate)
        state.events = sorted(
            merged,
            key=lambda item: (
                item.source_name.casefold(),
                item.listing_url,
                item.evidence.page_index,
                item.evidence.document_position.get("y", 0),
            ),
        )
        state.event_collection = collection
        return self.save(state)

    def set_event_decision(self, candidate_id: str, decision: Decision) -> ReviewState:
        state = self.load()
        match = next((item for item in state.events if item.candidate_id == candidate_id), None)
        if match is None:
            raise ValueError("event candidate not found")
        match.decision = decision
        match.reviewed_at = utc_now()
        return self.save(state)

    def append_feedback(self, raw: dict[str, Any]) -> EventFeedback:
        source = self.source(str(raw.get("source_id") or ""))
        listing_url = canonical_url(raw.get("listing_url"))
        allowed = {canonical_url(value) for value in source.get("listing_urls") or []}
        state = self.load()
        confirmed = {
            item.url
            for item in state.listing_pages
            if item.source_id == source.get("id") and item.decision == "confirmed"
        }
        if listing_url not in allowed and listing_url not in confirmed:
            raise ValueError("feedback listing URL is not configured or confirmed")
        feedback = EventFeedback(
            feedback_id=uuid.uuid4().hex,
            source_id=str(source.get("id")),
            source_name=str(source.get("name") or source.get("id")),
            listing_url=listing_url,
            page_url=canonical_url(raw.get("page_url")),
            selector=str(raw.get("selector") or "").strip(),
            selector_index=max(0, int(raw.get("selector_index") or 0)),
            selector_match_count=max(1, int(raw.get("selector_match_count") or 1)),
            document_position={
                key: int((raw.get("document_position") or {}).get(key) or 0)
                for key in ("x", "y", "width", "height")
            },
            text=str(raw.get("text") or "").strip()[:3000],
            href=str(raw.get("href") or "").strip()[:2000],
            created_at=utc_now(),
        )
        if not feedback.selector:
            raise ValueError("feedback selector must not be empty")
        state.feedback.insert(0, feedback)
        state.feedback = state.feedback[:500]
        self.save(state)
        return feedback


def _allowed_host(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in source.get("allowed_domains") or []
        )
    )


def collect_listing_pages(store: EventReviewStore) -> ReviewState:
    started = utc_now()
    candidates: dict[str, ListingPageCandidate] = {}
    errors: list[dict[str, str]] = []

    for source in store.inventory():
        source_id = str(source.get("id") or "")
        source_name = str(source.get("name") or source_id)
        for value in source.get("listing_urls") or []:
            url = canonical_url(value)
            candidate = ListingPageCandidate(
                candidate_id=stable_id(source_id, url),
                source_id=source_id,
                source_name=source_name,
                url=url,
                origin="configured",
                discovered_at=started,
            )
            candidates[candidate.candidate_id] = candidate

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                for source in store.inventory():
                    source_id = str(source.get("id") or "")
                    source_name = str(source.get("name") or source_id)
                    home = str(source.get("official_home") or "").strip()
                    if not home:
                        continue
                    try:
                        page.goto(home, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                        rows = page.evaluate(
                            LISTING_DISCOVERY_JS,
                            {"allowedDomains": source.get("allowed_domains") or []},
                        )
                        for row in rows:
                            url = canonical_url(row.get("url"))
                            if not _allowed_host(url, source):
                                continue
                            candidate_id = stable_id(source_id, url)
                            if candidate_id in candidates:
                                continue
                            candidates[candidate_id] = ListingPageCandidate(
                                candidate_id=candidate_id,
                                source_id=source_id,
                                source_name=source_name,
                                url=url,
                                origin="discovered",
                                link_text=str(row.get("link_text") or "")[:240],
                                discovered_at=started,
                            )
                    except Exception as exc:
                        errors.append({"source_id": source_id, "error": f"{type(exc).__name__}: {exc}"[:500]})
                context.close()
            finally:
                browser.close()
    except Exception as exc:
        errors.append({"source_id": "*", "error": f"{type(exc).__name__}: {exc}"[:500]})

    return store.replace_listing_pages(
        list(candidates.values()),
        {
            "started_at": started,
            "completed_at": utc_now(),
            "candidate_count": len(candidates),
            "errors": errors,
        },
    )


def _title(card: dict[str, Any]) -> str:
    for value in [*(card.get("headings") or []), card.get("link_text"), *((card.get("text_lines") or [])[:3])]:
        text = str(value or "").strip()
        if text:
            return text[:300]
    return "Untitled candidate"


def collect_event_candidates(store: EventReviewStore) -> ReviewState:
    state = store.load()
    confirmed = [item for item in state.listing_pages if item.decision == "confirmed"]
    if not confirmed:
        raise ValueError("no confirmed listing pages")

    sources = {str(source.get("id")): source for source in store.inventory()}
    started = utc_now()
    candidates: dict[str, EventCandidate] = {}
    errors: list[dict[str, str]] = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            for listing in confirmed:
                source = sources.get(listing.source_id)
                if source is None:
                    errors.append({"listing_url": listing.url, "error": "source_not_found"})
                    continue
                try:
                    page.goto(listing.url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    page.evaluate(PREPARE_PAGE_JS, {"maxRounds": max(0, LOAD_MORE_ROUNDS)})
                    cards = page.evaluate(
                        CARD_JS,
                        {
                            "allowedDomains": source.get("allowed_domains") or [],
                            "maxCards": 120,
                            "sourceId": listing.source_id,
                            "pageIndex": 0,
                            "adapter": source.get("adapter") or "rendered_dom_card",
                            "officialHome": source.get("official_home") or "",
                        },
                    )
                    evidence_by_id = page.evaluate(CARD_EVIDENCE_JS)
                    for card in cards:
                        detail_url = str(card.get("url") or "").strip()
                        if not detail_url.startswith(("http://", "https://")):
                            continue
                        evidence = evidence_by_id.get(str(card.get("id") or ""))
                        if not isinstance(evidence, dict) or not evidence.get("selector"):
                            continue
                        detail_url = canonical_url(urljoin(str(page.url), detail_url))
                        candidate_id = stable_id(listing.source_id, listing.url, detail_url, str(evidence.get("selector")), str(evidence.get("selector_index")))
                        candidates[candidate_id] = EventCandidate(
                            candidate_id=candidate_id,
                            source_id=listing.source_id,
                            source_name=listing.source_name,
                            listing_url=listing.url,
                            detail_url=detail_url,
                            title=_title(card),
                            evidence=EventEvidence(
                                selector=str(evidence.get("selector")),
                                selector_index=max(0, int(evidence.get("selector_index") or 0)),
                                selector_match_count=max(1, int(evidence.get("selector_match_count") or 1)),
                                document_position={key: int((evidence.get("document_position") or {}).get(key) or 0) for key in ("x", "y", "width", "height")},
                                viewport_position={key: int((evidence.get("viewport_position") or {}).get(key) or 0) for key in ("x", "y", "width", "height")},
                                page_index=max(0, int(card.get("page_index") or 0)),
                                page_url=canonical_url(card.get("page_url") or listing.url),
                                text=str(card.get("text") or "").strip()[:5000],
                            ),
                            collected_at=started,
                        )
                except Exception as exc:
                    errors.append({"listing_url": listing.url, "error": f"{type(exc).__name__}: {exc}"[:500]})
            context.close()
        finally:
            browser.close()

    return store.replace_events(
        list(candidates.values()),
        {
            "started_at": started,
            "completed_at": utc_now(),
            "confirmed_listing_count": len(confirmed),
            "candidate_count": len(candidates),
            "errors": errors,
        },
    )


__all__ = [
    "Decision",
    "EventCandidate",
    "EventFeedback",
    "EventReviewStore",
    "ListingPageCandidate",
    "ReviewState",
    "collect_event_candidates",
    "collect_listing_pages",
]
