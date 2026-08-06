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


# Preview performs one bounded pass over the selected page's main content. The same
# evaluation returns both candidates and stage counts, so a zero result has an exact
# page-scoped explanation without invoking the formal selector audit or full-page scan.
PREVIEW_LISTING_JS = r"""
async (args) => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const sourceId = clean(args.sourceId).toLowerCase();
  const allowed = (args.allowedDomains || [])
    .map(value => clean(value).replace(/^www\./, "").toLowerCase())
    .filter(Boolean);
  const listing = new URL(args.listingUrl || location.href, location.href);
  const root = document.querySelector("main") ||
    document.querySelector("[role='main']") || document.body;
  const maxEvents = Math.max(1, Math.min(Number(args.maxEvents || 40), 60));

  const emptyObserved = {
    final_url: location.href,
    page_title: clean(document.title),
    body_text_length: 0,
    visible_link_count: 0,
    same_domain_link_count: 0,
    detail_link_count: 0,
    extracted_card_count: 0,
    admitted_card_count: 0,
    marked_card_count: 0,
    cards_with_evidence: 0,
    cards_with_selector: 0,
    detail_link_examples: [],
  };
  if (!root) return {rows: [], observed: emptyObserved};

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

  const allowedUrl = raw => {
    try {
      const url = new URL(raw, location.href);
      const host = url.hostname.replace(/^www\./, "").toLowerCase();
      if (!allowed.some(domain => host === domain || host.endsWith("." + domain))) {
        return "";
      }
      url.hash = "";
      return url.href;
    } catch (error) {
      return "";
    }
  };

  const officialDetailUrl = raw => {
    const absolute = allowedUrl(raw);
    if (!absolute) return "";
    try {
      const url = new URL(absolute);
      const path = decodeURIComponent(url.pathname).replace(/\/$/, "").toLowerCase();
      const listingPath = decodeURIComponent(listing.pathname).replace(/\/$/, "").toLowerCase();
      if (!path || path === listingPath) return "";
      if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf|zip)$/i.test(path)) return "";
      const host = url.hostname.replace(/^www\./, "").toLowerCase();
      if (
        (host === "gardensbythebay.com.sg" ||
         host.endsWith(".gardensbythebay.com.sg")) &&
        /^\/(?:[a-z]{2}\/)?learn-with-us\/explore-resources(?:\/|$)/i.test(path)
      ) return "";
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

  const genericLinkText = value => /^(?:view|view details?|details?|learn more|read more|find out more|explore|book now|buy tickets?|tickets?)$/i.test(clean(value));

  const descriptiveAnchorTitle = anchor => {
    const values = [
      anchor.getAttribute("aria-label"),
      anchor.innerText,
      anchor.textContent,
      anchor.querySelector("img[alt]")?.getAttribute("alt"),
      anchor.getAttribute("title"),
    ].map(clean);
    return values.find(value =>
      value.length >= 4 && value.length <= 240 && !genericLinkText(value)
    ) || "";
  };

  const isArtScienceDetail = detailUrl => {
    if (sourceId !== "artscience") return false;
    try {
      const path = decodeURIComponent(new URL(detailUrl).pathname).replace(/\/$/, "");
      return /^\/museum\/(?:exhibitions|events|programmes|programs|experiences)\/[^/]+(?:\.html)?$/i.test(path);
    } catch (error) {
      return false;
    }
  };

  const repeatedBoundary = element => {
    const parent = element?.parentElement;
    if (!parent || !root.contains(parent)) return false;
    const siblings = Array.from(parent.children).filter(child =>
      child.tagName === element.tagName && visible(child) && child.querySelector("a[href]")
    );
    if (siblings.length < 2 || siblings.length > 24) return false;
    const classTokens = Array.from(element.classList || []).filter(token => token.length >= 3);
    if (classTokens.some(token => siblings.filter(child => child.classList.contains(token)).length >= 2)) {
      return true;
    }
    return siblings.filter(child => child.querySelector("h1,h2,h3,h4,h5,h6,img")).length >= 2;
  };

  const nearestCard = anchor => {
    const explicit = anchor.closest(
      "article,li,[class*='card' i],[class*='tile' i],[class*='event' i]," +
      "[class*='programme' i],[class*='program' i],[class*='exhibition' i]," +
      "[class*='listing' i],[class*='result' i],[class*='item' i]"
    );
    if (explicit && root.contains(explicit) && visible(explicit)) {
      return {element: explicit, strong_boundary: true};
    }

    let element = anchor;
    let fallback = null;
    for (let depth = 0; element && depth < 7; depth += 1) {
      if (element === root.parentElement) break;
      if (visible(element)) {
        const cardText = clean(element.innerText || element.textContent || "");
        const rect = element.getBoundingClientRect();
        if (cardText.length >= 12 && cardText.length <= 2200 && rect.height <= 1200) {
          if (repeatedBoundary(element)) {
            return {element, strong_boundary: true};
          }
          fallback = fallback || {element, strong_boundary: false};
        }
      }
      if (element === root) break;
      element = element.parentElement;
    }
    return fallback;
  };

  const rows = [];
  const seen = new Set();
  const detailExamples = [];
  const anchors = Array.from(root.querySelectorAll("a[href]"));
  let visibleLinkCount = 0;
  let sameDomainLinkCount = 0;
  let detailLinkCount = 0;
  let extractedCardCount = 0;
  let admittedCardCount = 0;

  for (const anchor of anchors) {
    if (!visible(anchor)) continue;
    visibleLinkCount += 1;
    if (allowedUrl(anchor.getAttribute("href"))) sameDomainLinkCount += 1;

    const detailUrl = officialDetailUrl(anchor.getAttribute("href"));
    if (!detailUrl) continue;
    detailLinkCount += 1;
    const directTitle = descriptiveAnchorTitle(anchor);
    if (detailExamples.length < 5) {
      detailExamples.push({
        text: directTitle || clean(anchor.innerText || anchor.textContent || anchor.getAttribute("aria-label")).slice(0, 160),
        url: detailUrl,
      });
    }
    if (rows.length >= maxEvents || seen.has(detailUrl)) continue;

    const artScienceTitledDetail = isArtScienceDetail(detailUrl) && Boolean(directTitle);
    let boundary = nearestCard(anchor);
    if (!boundary?.element && artScienceTitledDetail) {
      boundary = {element: anchor, strong_boundary: true, source_specific: true};
    }
    if (!boundary?.element) continue;
    extractedCardCount += 1;
    const card = boundary.element;
    const lines = linesFor(card);
    const when = lines.find(scheduleLine) || "";

    const cardHeading = Array.from(card.querySelectorAll("h1,h2,h3,h4,h5,h6"))
      .map(element => clean(element.innerText || element.textContent || ""))
      .find(value => value && !genericLinkText(value)) || "";
    const heading = artScienceTitledDetail ? directTitle : (cardHeading || directTitle);
    if (!heading || heading.length > 240) continue;

    // A rendered official list card with a usable title and official detail link is
    // authoritative for membership. ArtScience exposes descriptive exhibition links in
    // main content without the generic card/date structure used by other sources; the
    // source-specific route plus descriptive link title is its bounded listing evidence.
    if (!when && !boundary.strong_boundary && !artScienceTitledDetail) continue;
    admittedCardCount += 1;

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
      text: lines.join("\n") || heading,
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

  return {
    rows,
    observed: {
      final_url: location.href,
      page_title: clean(document.title),
      body_text_length: clean(root.innerText || root.textContent || "").length,
      visible_link_count: visibleLinkCount,
      same_domain_link_count: sameDomainLinkCount,
      detail_link_count: detailLinkCount,
      extracted_card_count: extractedCardCount,
      admitted_card_count: admittedCardCount,
      marked_card_count: rows.length,
      cards_with_evidence: rows.length,
      cards_with_selector: rows.length,
      detail_link_examples: detailExamples,
    },
  };
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


def _diagnostic(
    listing: Any,
    observed: dict[str, Any],
    *,
    final_url: str,
    http_status: int | None,
    candidate_count: int,
) -> _diagnostics.ListingRecognitionDiagnostic:
    diagnostic = _diagnostics.ListingRecognitionDiagnostic(
        source_id=listing.source_id,
        source_name=listing.source_name,
        listing_url=listing.url,
        final_url=str(observed.get("final_url") or final_url),
        page_title=str(observed.get("page_title") or ""),
        http_status=http_status,
        body_text_length=max(0, int(observed.get("body_text_length") or 0)),
        visible_link_count=max(0, int(observed.get("visible_link_count") or 0)),
        same_domain_link_count=max(0, int(observed.get("same_domain_link_count") or 0)),
        detail_link_count=max(0, int(observed.get("detail_link_count") or 0)),
        extracted_card_count=max(0, int(observed.get("extracted_card_count") or 0)),
        admitted_card_count=max(0, int(observed.get("admitted_card_count") or 0)),
        marked_card_count=max(0, int(observed.get("marked_card_count") or 0)),
        cards_with_evidence=max(0, int(observed.get("cards_with_evidence") or 0)),
        cards_with_selector=max(0, int(observed.get("cards_with_selector") or 0)),
        candidates_created=max(0, candidate_count),
        detail_incomplete=max(0, candidate_count),
        detail_link_examples=[
            {
                "text": str(item.get("text") or "")[:160],
                "url": str(item.get("url") or "")[:2000],
            }
            for item in observed.get("detail_link_examples") or []
            if isinstance(item, dict)
        ][:5],
    )
    return _diagnostics._finish(diagnostic)


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
    observed: dict[str, Any] = {}
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
            payload = page.evaluate(
                PREVIEW_LISTING_JS,
                {
                    "allowedDomains": source.get("allowed_domains") or [],
                    "listingUrl": listing.url,
                    "sourceId": listing.source_id,
                    "maxEvents": MAX_PREVIEW_EVENTS,
                },
            ) or {}
            if isinstance(payload, dict):
                rows = [item for item in payload.get("rows") or [] if isinstance(item, dict)]
                observed = payload.get("observed") or {}
            elif isinstance(payload, list):
                rows = [item for item in payload if isinstance(item, dict)]
        finally:
            browser.close()

    candidates: list[_review.EventCandidate] = []
    default_venue = str(source.get("default_venue") or source.get("name") or "")
    for index, raw in enumerate(rows):
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
                    selector_index=index,
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

    diagnostic = _diagnostic(
        listing,
        observed,
        final_url=final_url,
        http_status=http_status,
        candidate_count=len(candidates),
    )
    return store.replace_events(
        candidates,
        {
            "started_at": started,
            "completed_at": _review.utc_now(),
            "confirmed_listing_count": 1,
            "candidate_count": len(candidates),
            "preview_mode": "direct_single_page_main_content",
            "preview_card_policy": "rendered_title_and_official_detail_link",
            "preview_diagnostics_mode": "same_pass_main_content",
            "formal_collector_bypassed": True,
            "selector_audit_skipped": True,
            "listing_diagnostics_skipped": False,
            "detail_page_requests_skipped": len(candidates),
            "final_url": final_url,
            "http_status": http_status,
            "listing_diagnostics": [diagnostic.model_dump(mode="json")],
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
