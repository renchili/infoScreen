from __future__ import annotations

from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import preview_collector_authority as _preview

_APPLIED = False
_BASE_COLLECT = None


# ArtScience renders each activity as one or more links inside a visual content block.
# The title is frequently a sibling of the clicked image/link rather than text inside
# that anchor. The generic preview boundary therefore sees the URL but cannot prove a
# title/date pair. This source-specific pass keeps the same rendered-DOM authority:
# one official activity route, one nearest container containing only that canonical
# activity URL, and one descriptive title rendered inside that container.
ARTSCIENCE_PREVIEW_JS = r"""
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
      Number(style.opacity || 1) !== 0 && rect.width >= 24 && rect.height >= 12;
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

  const activityUrl = raw => {
    const absolute = allowedUrl(raw);
    if (!absolute) return "";
    try {
      const url = new URL(absolute);
      const path = decodeURIComponent(url.pathname).replace(/\/$/, "");
      const listingPath = decodeURIComponent(listing.pathname).replace(/\/$/, "");
      if (path.toLowerCase() === listingPath.toLowerCase()) return "";
      if (!/^\/museum\/(?:exhibitions|events|programmes|programs|experiences)\/[^/]+\.html$/i.test(path)) {
        return "";
      }
      return url.href;
    } catch (error) {
      return "";
    }
  };

  const scheduleLine = value => {
    const line = clean(value);
    if (!line || line.length > 180) return false;
    return /\b20\d{2}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b|\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2}\b|\b(?:daily|ongoing|permanent|today|tomorrow)\b/i.test(line);
  };

  const genericTitle = value => /^(?:view|view details?|details?|learn more|read more|find out more|explore|book now|buy tickets?|tickets?|view all|what'?s on|exhibitions?|programmes?|programs?|experiences?|available date)$/i.test(clean(value));
  const descriptiveTitle = value => {
    const title = clean(value);
    return title.length >= 4 && title.length <= 240 &&
      !genericTitle(title) && !scheduleLine(title);
  };

  const sameActivityAnchors = (element, detailUrl) => {
    const anchors = [];
    if (element.matches?.("a[href]")) anchors.push(element);
    anchors.push(...element.querySelectorAll("a[href]"));
    return anchors.filter(anchor => activityUrl(anchor.getAttribute("href")) === detailUrl);
  };

  const titleFrom = (element, detailUrl) => {
    const candidates = [];
    for (const anchor of sameActivityAnchors(element, detailUrl)) {
      candidates.push(
        anchor.getAttribute("aria-label"),
        anchor.getAttribute("title"),
        anchor.innerText,
        anchor.textContent,
        anchor.querySelector("img[alt]")?.getAttribute("alt"),
      );
    }
    for (const node of element.querySelectorAll(
      "h1,h2,h3,h4,h5,h6,[class*='title' i],[class*='heading' i],[class*='name' i]"
    )) {
      candidates.push(node.innerText, node.textContent, node.getAttribute("aria-label"));
    }
    for (const image of element.querySelectorAll("img[alt]")) {
      candidates.push(image.getAttribute("alt"));
    }
    return candidates.map(clean).find(descriptiveTitle) || "";
  };

  const boundaryFor = (anchor, detailUrl) => {
    let element = anchor;
    for (let depth = 0; element && depth < 9; depth += 1) {
      if (element === root.parentElement) break;
      if (visible(element)) {
        const rect = element.getBoundingClientRect();
        const textLength = clean(element.innerText || element.textContent || "").length;
        const urls = new Set(
          sameActivityAnchors(element, detailUrl)
            .map(candidate => activityUrl(candidate.getAttribute("href")))
            .filter(Boolean)
        );
        if (urls.size === 1 && urls.has(detailUrl) &&
            textLength <= 2400 && rect.height <= 1400) {
          const title = titleFrom(element, detailUrl);
          if (title) return {element, title};
        }
      }
      if (element === root) break;
      element = element.parentElement;
    }
    return null;
  };

  const linesFor = element => String(element.innerText || element.textContent || "")
    .split(/\n+/)
    .map(clean)
    .filter(Boolean)
    .filter((value, index, all) => all.indexOf(value) === index)
    .slice(0, 80);

  const anchors = Array.from(root.querySelectorAll("a[href]"));
  const rows = [];
  const seen = new Set();
  const detailExamples = [];
  let visibleLinkCount = 0;
  let sameDomainLinkCount = 0;
  let detailLinkCount = 0;
  let extractedCardCount = 0;

  for (const anchor of anchors) {
    if (!visible(anchor)) continue;
    visibleLinkCount += 1;
    if (allowedUrl(anchor.getAttribute("href"))) sameDomainLinkCount += 1;

    const detailUrl = activityUrl(anchor.getAttribute("href"));
    if (!detailUrl) continue;
    detailLinkCount += 1;
    if (rows.length >= maxEvents || seen.has(detailUrl)) continue;

    const boundary = boundaryFor(anchor, detailUrl);
    if (!boundary) {
      if (detailExamples.length < 5) {
        detailExamples.push({text: "", url: detailUrl});
      }
      continue;
    }
    extractedCardCount += 1;

    const lines = linesFor(boundary.element);
    const when = lines.find(scheduleLine) || "";
    const summary = lines.find(line =>
      line !== boundary.title && line !== when &&
      !genericTitle(line) && line.length >= 24 && line.length <= 360
    ) || "";
    const rect = boundary.element.getBoundingClientRect();
    const index = rows.length;
    boundary.element.setAttribute("data-infoscreen-preview-index", String(index));
    rows.push({
      title: boundary.title,
      when,
      where: "",
      summary,
      detail_url: detailUrl,
      text: lines.join("\n") || boundary.title,
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
    if (detailExamples.length < 5) {
      detailExamples.push({text: boundary.title, url: detailUrl});
    }
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
      admitted_card_count: rows.length,
      marked_card_count: rows.length,
      cards_with_evidence: rows.length,
      cards_with_selector: rows.length,
      detail_link_examples: detailExamples,
    },
  };
}
"""


def _is_artscience_preview(store: _review.EventReviewStore) -> bool:
    if not store.root.name.startswith("infoscreen-event-preview-"):
        return False
    try:
        state = store.load()
    except Exception:
        return False
    selected = [item for item in state.listing_pages if item.decision == "confirmed"]
    return len(selected) == 1 and selected[0].source_id == "artscience"


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    if not _is_artscience_preview(store):
        return _BASE_COLLECT(store)

    original_script = _preview.PREVIEW_LISTING_JS
    _preview.PREVIEW_LISTING_JS = ARTSCIENCE_PREVIEW_JS
    try:
        return _BASE_COLLECT(store)
    finally:
        _preview.PREVIEW_LISTING_JS = original_script


def apply() -> None:
    global _APPLIED, _BASE_COLLECT
    if _APPLIED:
        _diagnostics.collect_event_candidates = collect_event_candidates
        return

    _BASE_COLLECT = _diagnostics.collect_event_candidates
    _diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = ["ARTSCIENCE_PREVIEW_JS", "apply", "collect_event_candidates"]
