from __future__ import annotations

from typing import Any

from . import browser as _browser

_APPLIED = False

PREVIEW_NAV_TIMEOUT_MS = 15_000
PREVIEW_DOM_TIMEOUT_MS = 15_000
PREVIEW_PREPARE_PAGE_JS = r"""
async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const body = document.body;
  if (!body) return {scrolls: 0, height: 0};

  // Preview verifies that the selected URL exposes activity cards. It does not run
  // the complete collector's 80-round expansion budget. One bottom scroll gives
  // intersection observers and initial lazy-loaded cards a chance to render.
  window.scrollTo(0, body.scrollHeight);
  await sleep(700);
  window.scrollTo(0, 0);
  await sleep(150);
  return {scrolls: 1, height: body.scrollHeight};
}
"""

# The complete collector's generic CARD_JS scores every visible document link against
# several ancestors. Each score scans all descendant links again, and sorting repeats
# those scans. Large pages with duplicated desktop/mobile navigation can therefore
# spend minutes in one unbounded page.evaluate call. Preview only needs authoritative
# cards from the selected list page, so this extractor performs one main-content pass,
# caches each container's text and URLs, and never sorts or parses embedded JSON.
PREVIEW_CARD_JS = r"""
(args) => {
  const allowedDomains = (args.allowedDomains || [])
    .map(value => String(value || "").replace(/^www\./, "").toLowerCase())
    .filter(Boolean);
  const maxCards = Math.max(1, Math.min(Number(args.maxCards || 60), 80));
  const sourceId = String(args.sourceId || "source");
  const pageIndex = Number(args.pageIndex || 0);
  const root = document.querySelector("main") ||
    document.querySelector("[role='main']") || document.body;

  const clean = value => String(value || "")
    .replace(/[ \t\f\v]+/g, " ")
    .replace(/\n\s+/g, "\n")
    .replace(/\s+\n/g, "\n")
    .trim();
  const oneLine = value => clean(value).replace(/\s+/g, " ").trim();
  const dateLike = value => /\b20\d{2}\b|\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/i.test(value);
  const excludedContainer = element => Boolean(element.closest(
    "header, nav, footer, form, dialog, [role='navigation'], [role='dialog'], " +
    "[class*='breadcrumb' i], [class*='cookie' i], [class*='newsletter' i]"
  ));
  const visible = element => {
    if (!element || excludedContainer(element)) return false;
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden" ||
        Number(style.opacity || 1) === 0) return false;
    const rect = element.getBoundingClientRect();
    return rect.width >= 40 && rect.height >= 18;
  };
  const sameDomain = raw => {
    try {
      const host = new URL(raw, location.href).hostname
        .replace(/^www\./, "").toLowerCase();
      return allowedDomains.some(domain =>
        host === domain || host.endsWith("." + domain)
      );
    } catch (error) {
      return false;
    }
  };
  const canonical = raw => {
    try {
      const url = new URL(raw, location.href);
      url.hash = "";
      return url.href;
    } catch (error) {
      return "";
    }
  };
  const isDetailUrl = raw => {
    const value = canonical(raw);
    if (!value || !sameDomain(value)) return false;
    const url = new URL(value);
    const current = new URL(location.href);
    const path = decodeURIComponent(url.pathname).replace(/\/$/, "").toLowerCase();
    const currentPath = decodeURIComponent(current.pathname)
      .replace(/\/$/, "").toLowerCase();
    if (!path || path === currentPath) return false;
    if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$/i.test(path)) return false;
    if (/[?&](?:category|filter|time|date|type|page)=/i.test(url.search)) return false;
    const leaf = (path.split("/").filter(Boolean).pop() || "")
      .replace(/\.html$/, "");
    return !new Set([
      "", "whats-on", "whatson", "overview", "view-all", "events", "event",
      "exhibition", "exhibitions", "programme", "programmes", "program",
      "programs", "activities", "activity", "guided-tours"
    ]).has(leaf);
  };
  const textHash = value => {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16);
  };

  const lineCache = new WeakMap();
  const urlCache = new WeakMap();
  const textLines = element => {
    if (lineCache.has(element)) return lineCache.get(element);
    const lines = String(element.innerText || element.textContent || "")
      .replace(/\r/g, "\n")
      .split("\n")
      .map(oneLine)
      .filter(Boolean);
    lineCache.set(element, lines);
    return lines;
  };
  const detailUrls = element => {
    if (urlCache.has(element)) return urlCache.get(element);
    const anchors = [];
    if (element.matches && element.matches("a[href]")) anchors.push(element);
    for (const anchor of element.querySelectorAll("a[href]")) anchors.push(anchor);
    const urls = [];
    for (const anchor of anchors) {
      const value = canonical(anchor.getAttribute("href"));
      if (isDetailUrl(value) && !urls.includes(value)) urls.push(value);
      if (urls.length > 1) break;
    }
    urlCache.set(element, urls);
    return urls;
  };
  const cardContainer = (anchor, detailUrl) => {
    let element = anchor;
    for (let depth = 0; element && depth < 9; depth += 1) {
      if (element === root.parentElement) break;
      if (visible(element)) {
        const lines = textLines(element);
        const urls = detailUrls(element);
        const text = lines.join(" ");
        const rect = element.getBoundingClientRect();
        if (
          urls.length === 1 && urls[0] === detailUrl && dateLike(text) &&
          text.length >= 12 && text.length <= 2600 &&
          rect.width >= 80 && rect.height >= 35 && rect.height <= 1200
        ) {
          return element;
        }
      }
      if (element === root) break;
      element = element.parentElement;
    }
    return null;
  };

  const output = [];
  const seenUrls = new Set();
  const anchors = Array.from(root.querySelectorAll("a[href]"));
  for (const anchor of anchors) {
    if (output.length >= maxCards || !visible(anchor)) continue;
    const detailUrl = canonical(anchor.getAttribute("href"));
    if (!isDetailUrl(detailUrl) || seenUrls.has(detailUrl)) continue;
    const card = cardContainer(anchor, detailUrl);
    if (!card) continue;

    const lines = textLines(card);
    const headings = Array.from(card.querySelectorAll("h1,h2,h3,h4,h5,h6"))
      .map(element => oneLine(element.innerText || element.textContent || ""))
      .filter(Boolean)
      .slice(0, 8);
    const imageAlts = Array.from(card.querySelectorAll("img[alt]"))
      .map(image => oneLine(image.getAttribute("alt")))
      .filter(Boolean)
      .slice(0, 8);
    const linkText = oneLine(
      anchor.innerText || anchor.textContent || anchor.getAttribute("aria-label") || ""
    );
    const text = lines.join("\n");
    const id = `${sourceId}-${pageIndex}-preview-${textHash(detailUrl + text.slice(0, 500))}`;
    const rect = card.getBoundingClientRect();
    card.setAttribute("data-infoscreen-card-id", id);
    output.push({
      id,
      url: detailUrl,
      link_text: linkText,
      headings,
      image_alts: imageAlts,
      text,
      text_lines: lines,
      detail_url_count: 1,
      detail_urls: [detailUrl],
      page_index: pageIndex,
      page_url: location.href,
      rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      role: "detail",
      extraction_mode: "detail_link"
    });
    seenUrls.add(detailUrl);
  }
  return output;
}
"""


def _bind_final_browser_runtime_to_review() -> None:
    """Make Studio use the final browser rules, not import-time snapshots.

    ``event_review`` imports browser constants with ``from .browser import ...``.
    Several authorities intentionally rewrite the browser JavaScript after that
    module has already been imported, so its local names otherwise remain stale.
    This binding is the single final handoff after every browser authority has run.
    """
    from . import event_review as review

    for name in (
        "CARD_JS",
        "CLICK_NEXT_PAGE_JS",
        "DETAIL_CARD_JS",
        "DOM_TIMEOUT_MS",
        "LOAD_MORE_ROUNDS",
        "MAX_LISTING_PAGES",
        "NAV_TIMEOUT_MS",
        "NEXT_WAIT_MS",
        "PREPARE_PAGE_JS",
        "launch_chromium",
        "merge_detail_payload",
    ):
        setattr(review, name, getattr(_browser, name))


def _is_explicit_open_schedule(value: object) -> bool:
    """Preserve the existing explicit open-ended schedule policy."""
    from . import extract

    text = extract.clean(value).casefold()
    return text.startswith("from ") or "ongoing" in text or "permanent" in text


def _filter_final_expired_events(state, effective):
    """Use the final detail parser for the final HTTP lifecycle decision."""
    from . import extract

    active = []
    removed = 0
    for candidate in state.events:
        if _is_explicit_open_schedule(candidate.when):
            active.append(candidate)
            continue
        dates = effective._line_dates(candidate.when)
        if dates and max(dates) < extract.TODAY:
            removed += 1
            continue
        active.append(candidate)

    state.events = active
    metadata = dict(state.event_collection)
    metadata["candidate_count"] = len(active)
    metadata["expired_candidate_count"] = int(
        metadata.get("expired_candidate_count") or 0
    ) + removed
    state.event_collection = metadata
    return state


def _bind_final_event_collector() -> None:
    """Pin every HTTP collection run to the final detail owner.

    Normal confirmed-page collection keeps the final detail owner and its complete
    listing-expansion budget. An isolated preview uses a linear main-content card
    extractor and does not open every detail page or traverse pagination.
    """
    from . import detail_date_authority as detail_dates
    from . import event_review as review
    from . import event_review_diagnostics as diagnostics
    from . import extract
    from . import listing_provenance_authority as provenance
    from . import review_effective_fields_authority as effective
    from .detail_summary_authority import useful_event_summary

    def preview_detail_candidate(
        context: Any,
        source: dict[str, Any],
        listing_url: str,
        raw_url: str,
        card: dict[str, Any],
    ) -> dict[str, str]:
        """Build one preview row from listing evidence without detail navigation."""

        requested_url = provenance.listing_detail_url(listing_url, raw_url)
        if not requested_url:
            raise ValueError("detail URL is not a safe HTTP(S) target from the listing")

        listing = detail_dates._listing_fields(source, card)
        title = extract.clean(listing.get("title")) or review._listing_title(card)
        when = extract.clean(listing.get("when"))
        where = extract.clean(listing.get("where"))
        summary = useful_event_summary(listing.get("summary")) or ""
        missing = [
            name
            for name, value in (("title", title), ("when", when), ("where", where))
            if not value
        ]
        suffix = "_missing_" + "_and_".join(missing) if missing else ""
        return {
            "detail_url": requested_url,
            "title": title,
            "when": when,
            "where": where,
            "summary": summary,
            "detail_status": "incomplete",
            "detail_error": "preview_listing_evidence_only" + suffix,
            "detail_page_title": "",
        }

    def collect_event_candidates(store):
        effective.apply()
        preview_listing_only = store.root.name.startswith("infoscreen-event-preview-")
        review._detail_candidate = (
            preview_detail_candidate
            if preview_listing_only
            else effective.detail_candidate
        )

        original_preview_runtime: dict[str, Any] = {}
        if preview_listing_only:
            for name in (
                "CARD_JS",
                "MAX_LISTING_PAGES",
                "LOAD_MORE_ROUNDS",
                "NAV_TIMEOUT_MS",
                "DOM_TIMEOUT_MS",
                "PREPARE_PAGE_JS",
            ):
                original_preview_runtime[name] = getattr(_browser, name)
            _browser.CARD_JS = PREVIEW_CARD_JS
            _browser.MAX_LISTING_PAGES = 1
            _browser.LOAD_MORE_ROUNDS = 0
            _browser.NAV_TIMEOUT_MS = PREVIEW_NAV_TIMEOUT_MS
            _browser.DOM_TIMEOUT_MS = PREVIEW_DOM_TIMEOUT_MS
            _browser.PREPARE_PAGE_JS = PREVIEW_PREPARE_PAGE_JS

        try:
            state = diagnostics.collect_event_candidates(store)
        finally:
            review._detail_candidate = effective.detail_candidate
            for name, value in original_preview_runtime.items():
                setattr(_browser, name, value)

        state = _filter_final_expired_events(state, effective)
        state.event_collection = {
            **state.event_collection,
            "detail_owner_module": effective.detail_candidate.__module__,
            "detail_owner_name": effective.detail_candidate.__qualname__,
            "detail_owner_file": str(effective.__file__),
            "preview_detail_mode": (
                "listing_evidence_only" if preview_listing_only else "full_detail"
            ),
            "preview_listing_mode": (
                "single_page_linear_main_dom" if preview_listing_only else "complete"
            ),
            "preview_card_mode": (
                "cached_linear_main_content" if preview_listing_only else "complete"
            ),
            "detail_page_requests_skipped": (
                len(state.events) if preview_listing_only else 0
            ),
        }
        store.save(state)
        return state

    review.collect_event_candidates = collect_event_candidates


def apply() -> None:
    """Install the shared Local Events browser and review-backend bootstrap.

    The Surface has observed Chromium navigation failures with
    ERR_HTTP2_PROTOCOL_ERROR on official Event sites. Collection starts in
    HTTP/1.1 mode directly. Browser operations are clamped to the active source and
    global collection deadlines so timed-out workers close before systemd's outer
    service limit. Listing navigation accepts a readable rendered document even when
    lifecycle events do not settle. Review detail navigations use a bounded batch,
    are consumed synchronously by the existing blocking reader, and are closed
    immediately after extraction. A per-context URL cache prevents overlapping
    listing pages from downloading the same detail document repeatedly. Coverage,
    source, date, detail-field, section-aware summary, listing-provenance,
    listing-membership, dynamic-listing, card, and link authorities are applied before
    their final values are bound into Review Studio.
    """
    global _APPLIED
    if _APPLIED:
        return

    def launch_chromium_http1(playwright: Any):
        from .resilient_navigation_authority import apply as apply_navigation

        apply_navigation()
        return _browser.launch_playwright_chromium(
            playwright,
            headless=True,
            args=["--disable-http2"],
        )

    _browser.launch_chromium = launch_chromium_http1

    from .deadline_authority import apply as apply_deadline_authority
    apply_deadline_authority()

    from .complete_collection_authority import apply as apply_complete_collection
    apply_complete_collection()

    from .detail_date_authority import apply as apply_detail_date_authority
    apply_detail_date_authority()

    from .detail_payload_authority import apply as apply_detail_payload_authority
    apply_detail_payload_authority()

    from .detail_summary_authority import apply as apply_detail_summary_authority
    apply_detail_summary_authority()

    from .review_detail_navigation_authority import (
        apply as apply_review_detail_navigation_authority,
    )
    apply_review_detail_navigation_authority()

    from .dynamic_listing_authority import apply as apply_dynamic_listing_authority
    apply_dynamic_listing_authority()

    from .open_ended_date_authority import apply as apply_open_ended_date_authority
    apply_open_ended_date_authority()

    from .open_detail_fields_authority import apply as apply_open_detail_fields_authority
    apply_open_detail_fields_authority()

    from .gardens_field_authority import apply as apply_gardens_field_authority
    apply_gardens_field_authority()

    from .listing_provenance_authority import apply as apply_listing_provenance_authority
    apply_listing_provenance_authority()

    from .listing_membership_authority import apply as apply_listing_membership_authority
    apply_listing_membership_authority()

    from .mandai_listing_authority import apply as apply_mandai_listing_authority
    apply_mandai_listing_authority()

    from .structural_link_authority import apply as apply_structural_link_authority
    apply_structural_link_authority()

    from .listing_url_authority import apply as apply_listing_url_authority
    apply_listing_url_authority()

    # Apply this last over the composed event authority so explicit Where/Location
    # labels and public URL rewrites survive every source/membership wrapper.
    from .detail_authority import apply as apply_detail_authority
    apply_detail_authority()

    # event_review was imported before the final JavaScript rewrites above. Rebind
    # only after all browser and event authorities have their final values.
    _bind_final_browser_runtime_to_review()

    from .review_effective_fields_authority import (
        apply as apply_review_effective_fields_authority,
    )
    apply_review_effective_fields_authority()

    from .event_review_diagnostics import apply as apply_event_review_diagnostics
    apply_event_review_diagnostics()

    from .review_summary_authority import apply as apply_review_summary_authority
    apply_review_summary_authority()

    from .review_publish_authority import apply as apply_review_publish_authority
    apply_review_publish_authority()

    # This is the final HTTP handoff. The server imports the wrapper from event_review
    # after apply() returns, and the wrapper pins every POST to the effective owner.
    _bind_final_event_collector()
    _APPLIED = True


__all__ = [
    "PREVIEW_CARD_JS",
    "PREVIEW_DOM_TIMEOUT_MS",
    "PREVIEW_NAV_TIMEOUT_MS",
    "PREVIEW_PREPARE_PAGE_JS",
    "apply",
]
