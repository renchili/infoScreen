from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics

_APPLIED = False
_BASE_COLLECT = None
PREVIEW_PAGE_TIMEOUT_MS = 20_000
PREVIEW_SETTLE_MS = 1_200
MAX_PREVIEW_EVENTS = 40


# Preview is deliberately not a reduced version of the formal collector. It performs
# one bounded pass over the selected page's main content and returns only the fields
# needed by the Review Studio preview. Selector auditing, full-page diagnostics,
# pagination, structured-payload crawling, and detail-page navigation are excluded.
PREVIEW_LISTING_JS = r"""
async (args) => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const allowed = (args.allowedDomains || [])
    .map(value => clean(value).replace(/^www\./, "").toLowerCase())
    .filter(Boolean);
  const listing = new URL(args.listingUrl || location.href, location.href);
  const root = document.querySelector("main") ||
    document.querySelector("[role='main']") || document.body;
  const maxEvents = Math.max(1, Math.min(Number(args.maxEvents || 40), 60));

  if (!root) return [];

  window.scrollTo(0, root.scrollHeight || document.body.scrollHeight);
  await sleep(650);
  window.scrollTo(0, 0);
  await sleep(150);

  const visible = element => {
    if (!element || element.closest(
      "header,nav,footer,form,dialog,[role='navigation'],[role='dialog']," +
      "[class*='breadcrumb' i],[class*='cookie' i],[class*='newsletter' i]"
    )) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 40 && rect.height >= 18;
  };

  const officialUrl = raw => {
    try {
      const url = new URL(raw, location.href);
      const host = url.hostname.replace(/^www\./, "").toLowerCase();
      if (!allowed.some(domain => host === domain || host.endsWith("." + domain))) {
        return "";
      }
      url.hash = "";
      const path = decodeURIComponent(url.pathname).replace(/\/$/, "").toLowerCase();
      const listingPath = decodeURIComponent(listing.pathname).replace(/\/$/, "").toLowerCase();
      if (!path || path === listingPath) return "";
      if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf|zip)$/i.test(path)) return "";
      return url.href;
    } catch (error) {
      return "";
    }
  };

  const scheduleLine = value => {
    const line = clean(value);
    if (!line || line.length > 180) return false;
    return /\b20\d{2}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b|\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2}\b|\b(?:daily|ongoing|permanent|today|tomorrow)\b|\b(?:mon|monday|tue|tuesday|wed|wednesday|thu|thursday|fri|friday|sat|saturday|sun|sunday)\s*[–—-]\s*(?:mon|monday|tue|tuesday|wed|wednesday|thu|thursday|fri|friday|sat|saturday|sun|sunday)\b/i.test(line);
  };

  const linesFor = element => String(element.innerText || element.textContent || "")
    .split(/\n+/)
    .map(clean)
    .filter(Boolean)
    .filter((value, index, all) => all.indexOf(value) === index)
    .slice(0, 80);

  const nearestCard = anchor => {
    const explicit = anchor.closest(
      "article,li,[class*='card' i],[class*='tile' i],[class*='event' i]," +
      "[class*='programme' i],[class*='program' i],[class*='exhibition' i]," +
      "[class*='listing' i],[class*='result' i],[class*='item' i]"
    );
    if (explicit && root.contains(explicit) && visible(explicit)) return explicit;

    let element = anchor;
    for (let depth = 0; element && depth < 6; depth += 1) {
      if (element === root.parentElement) break;
      if (visible(element)) {
        const text = clean(element.innerText || element.textContent || "");
        const rect = element.getBoundingClientRect();
        if (text.length >= 12 && text.length <= 2200 && rect.height <= 1200) {
          return element;
        }
      }
      if (element === root) break;
      element = element.parentElement;
    }
    return null;
  };

  const rows = [];
  const seen = new Set();
  for (const anchor of root.querySelectorAll("a[href]")) {
    if (rows.length >= maxEvents || !visible(anchor)) continue;
    const detailUrl = officialUrl(anchor.getAttribute("href"));
    if (!detailUrl || seen.has(detailUrl)) continue;

    const card = nearestCard(anchor);
    if (!card) continue;
    const lines = linesFor(card);
    const when = lines.find(scheduleLine) || "";
    if (!when) continue;

    const heading = Array.from(card.querySelectorAll("h1,h2,h3,h4,h5,h6"))
      .map(element => clean(element.innerText || element.textContent || ""))
      .find(Boolean) || clean(anchor.innerText || anchor.textContent || anchor.getAttribute("aria-label"));
    if (!heading || heading.length > 240) continue;

    const summary = lines.find(line =>
      line !== heading && line !== when && line.length >= 24 && line.length <= 360
    ) || "";
    const rect = card.getBoundingClientRect();
    const index = rows.length;
    card.setAttribute("data-infoscreen-preview-index", String(index));
    rows.push({
      title: heading,
      when,
      where: "",
      summary,
      detail_url: detailUrl,
      text: lines.join("\n"),
      selector: `[data-infoscreen-preview-index="${index}"]`,
      document_position: {
        x: Math.round(rect.x + window.scrollX),
        y: Math.round(rect.y + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      viewport_position: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
    });
    seen.add(detailUrl);
  }
  return rows;
}
"""


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


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _collect_preview(store: _review.EventReviewStore) -> _review.ReviewState:
    state = store.load()
    confirmed = [item for item in state.listing_pages if item.decision == "confirmed"]
    if len(confirmed) != 1:
        raise ValueError("preview requires exactly one selected listing page")

    listing = confirmed[0]
    source = store.source(listing.source_id)
    if not _host_allowed(listing.url, source):
        raise ValueError("listing page is outside the source allow-list")

    started = _review.utc_now()
    rows: list[dict[str, Any]] = []
    final_url = listing.url
    http_status: int | None = None

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 1200},
                device_scale_factor=1,
            )
            response = page.goto(
                listing.url,
                wait_until="domcontentloaded",
                timeout=PREVIEW_PAGE_TIMEOUT_MS,
            )
            if response is not None:
                http_status = int(response.status)
                if http_status >= 400:
                    raise ValueError(f"listing_http_status_{http_status}")
            page.wait_for_timeout(PREVIEW_SETTLE_MS)
            final_url = str(page.url)
            if not _host_allowed(final_url, source):
                raise ValueError("listing page redirected outside the source allow-list")
            rows = page.evaluate(
                PREVIEW_LISTING_JS,
                {
                    "allowedDomains": source.get("allowed_domains") or [],
                    "listingUrl": listing.url,
                    "maxEvents": MAX_PREVIEW_EVENTS,
                },
            ) or []
        finally:
            browser.close()

    candidates: list[_review.EventCandidate] = []
    default_venue = str(source.get("default_venue") or source.get("name") or "")
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        detail_url = str(raw.get("detail_url") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not title or not _host_allowed(detail_url, source):
            continue
        document_position = raw.get("document_position") or {}
        viewport_position = raw.get("viewport_position") or {}
        candidates.append(
            _review.EventCandidate(
                candidate_id=_review.stable_id(
                    listing.source_id,
                    listing.url,
                    detail_url,
                ),
                source_id=listing.source_id,
                source_name=listing.source_name,
                listing_url=listing.url,
                detail_url=detail_url,
                title=title[:300],
                when=str(raw.get("when") or "")[:180],
                where=str(raw.get("where") or default_venue)[:300],
                summary=str(raw.get("summary") or "")[:500],
                detail_status="incomplete",
                detail_error="preview_listing_evidence_only",
                detail_page_title="",
                evidence=_review.EventEvidence(
                    selector=str(raw.get("selector") or "preview-card"),
                    selector_index=0,
                    selector_match_count=1,
                    document_position={
                        key: int(document_position.get(key) or 0)
                        for key in ("x", "y", "width", "height")
                    },
                    viewport_position={
                        key: int(viewport_position.get(key) or 0)
                        for key in ("x", "y", "width", "height")
                    },
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
            "preview_mode": "direct_single_page_main_content",
            "formal_collector_bypassed": True,
            "selector_audit_skipped": True,
            "listing_diagnostics_skipped": True,
            "detail_page_requests_skipped": len(candidates),
            "final_url": final_url,
            "http_status": http_status,
            "errors": [],
        },
    )


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    if _preview_store(store):
        return _collect_preview(store)
    return _BASE_COLLECT(store)


def apply() -> None:
    global _APPLIED, _BASE_COLLECT
    if _APPLIED:
        _diagnostics.collect_event_candidates = collect_event_candidates
        return
    _BASE_COLLECT = _diagnostics.collect_event_candidates
    _diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = [
    "MAX_PREVIEW_EVENTS",
    "PREVIEW_LISTING_JS",
    "PREVIEW_PAGE_TIMEOUT_MS",
    "apply",
    "collect_event_candidates",
]
