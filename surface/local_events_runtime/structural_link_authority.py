from __future__ import annotations

from . import event_review_diagnostics as _diagnostics
from . import listing_url_authority
from . import browser as _browser

_APPLIED = False

_CARD_HELPER_MARKER = "  function scoreContainer(el, anchor) {"
_ACTIVITY_CARD_HELPERS = r'''  function activityAnchorTitle(anchor) {
    const preferred = anchor.querySelector(".title");
    const candidates = [
      preferred,
      ...Array.from(anchor.querySelectorAll("h1,h2,h3,h4,[class*='title' i]")),
    ].filter(Boolean);
    for (const node of candidates) {
      const value = oneLine(node.innerText || node.textContent || "");
      if (titleLooksUseful(value)) return value;
    }
    return "";
  }

  function activityCardAnchor(anchor) {
    if (!anchor || !visible(anchor)) return false;
    const rect = anchor.getBoundingClientRect();
    const lines = textLines(anchor);
    const text = lines.join(" ");
    if (rect.width < 120 || rect.height < 45 || rect.height > 1200) return false;
    if (text.length < 20 || text.length > 3500 || !hasDateText(text)) return false;

    const attrs = oneLine([
      anchor.className,
      anchor.id,
      anchor.getAttribute("role"),
      anchor.getAttribute("aria-label"),
    ].join(" "));
    const title = activityAnchorTitle(anchor);
    if (!title) return false;

    const semanticClass = /\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attrs);
    const titleNode = anchor.querySelector(".title,h1,h2,h3,h4,[class*='title' i]");
    const detailNode = anchor.querySelector(".detail,time,[class*='date' i],[class*='time' i]");
    const infoNode = anchor.querySelector(".info,address,[class*='venue' i],[class*='location' i]");
    return Boolean(semanticClass || (titleNode && (detailNode || infoNode)));
  }

'''

_OLD_ANCHOR_LOOP = r'''  for (const a of anchors) {
    const abs = new URL(a.getAttribute("href"), document.location.href).href;
    if (!officialDetailUrl(abs)) continue;
    const card = bestCard(a);
    const listingDetailUrls = detailUrls(card);
    if (listingDetailUrls.length !== 1 || listingDetailUrls[0] !== abs) continue;
    if (!hasDateText(textLines(card).join(" "))) continue;
    const linkText = oneLine(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    push(out, seen, card, abs, linkText, "detail_link");
    if (out.length >= maxCards) break;
  }'''

_NEW_ANCHOR_LOOP = r'''  for (const a of anchors) {
    let abs = "";
    try { abs = new URL(a.getAttribute("href"), document.location.href).href; } catch { continue; }
    if (!sameDomain(abs)) continue;

    // A complete rendered activity card is positive evidence by itself. Do not
    // reject it merely because the site's URL path does not match our route words.
    const directActivityCard = activityCardAnchor(a);
    if (!directActivityCard && !officialDetailUrl(abs)) continue;

    const card = directActivityCard ? a : bestCard(a);
    const listingDetailUrls = detailUrls(card);
    if (listingDetailUrls.length !== 1 || listingDetailUrls[0] !== abs) continue;
    if (!hasDateText(textLines(card).join(" "))) continue;
    const linkText = directActivityCard
      ? activityAnchorTitle(a)
      : oneLine(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    push(out, seen, card, abs, linkText, "detail_link");
    if (out.length >= maxCards) break;
  }'''

_OLD_DIAGNOSTIC_FILTER = (
    '  const detailAnchors = sameDomainAnchors.filter(anchor => '
    'pathRole(anchor.getAttribute("href") || "") === "detail");'
)

_CONTENT_DIAGNOSTIC_FILTER = r'''  const listingUrl = new URL(location.href);
  const cleanPath = value => decodeURIComponent(String(value || "")).replace(/\/+$/, "");
  const listingPath = cleanPath(listingUrl.pathname);
  const listingStem = listingPath.replace(/\.html?$/i, "");
  const titleUseful = value => {
    const title = clean(value);
    return title.length >= 4 && title.length <= 180 && !/^(events?|exhibitions?|programmes?|programs?|activities?|overview|what'?s on|view all|read more|learn more|book now)$/i.test(title);
  };
  const hasDateText = value => /\b20\d{2}\b|\b\d{1,2}\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/i.test(clean(value));
  const activityCardAnchor = anchor => {
    const rect = anchor.getBoundingClientRect();
    const text = clean(anchor.innerText || anchor.textContent || "");
    if (rect.width < 120 || rect.height < 45 || rect.height > 1200 || !hasDateText(text)) return false;
    const preferred = anchor.querySelector(".title");
    const titleNode = preferred || anchor.querySelector("h1,h2,h3,h4,[class*='title' i]");
    const title = clean(titleNode?.innerText || titleNode?.textContent || "");
    if (!titleUseful(title)) return false;
    const attrs = clean([anchor.className, anchor.id, anchor.getAttribute("role")].join(" "));
    const semanticClass = /\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attrs);
    const detailNode = anchor.querySelector(".detail,time,[class*='date' i],[class*='time' i]");
    const infoNode = anchor.querySelector(".info,address,[class*='venue' i],[class*='location' i]");
    return Boolean(semanticClass || (titleNode && (detailNode || infoNode)));
  };
  const detailAnchors = sameDomainAnchors.filter(anchor => {
    if (activityCardAnchor(anchor)) return true;
    let target;
    try {
      target = new URL(anchor.getAttribute("href") || "", location.href);
    } catch {
      return false;
    }
    const targetPath = cleanPath(target.pathname);
    if (!targetPath || targetPath === listingPath) return false;
    if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$/i.test(targetPath)) return false;

    const role = pathRole(target.href);
    if (role === "listing") return false;
    if (role === "detail") return true;
    return Boolean(listingStem && targetPath.startsWith(listingStem + "/"));
  });'''


def _patch_card_js() -> None:
    card_js = _browser.CARD_JS
    if _ACTIVITY_CARD_HELPERS not in card_js:
        if _CARD_HELPER_MARKER not in card_js:
            raise RuntimeError("activity_card_helper_marker_missing")
        card_js = card_js.replace(
            _CARD_HELPER_MARKER,
            _ACTIVITY_CARD_HELPERS + _CARD_HELPER_MARKER,
            1,
        )
    if _OLD_ANCHOR_LOOP in card_js:
        card_js = card_js.replace(_OLD_ANCHOR_LOOP, _NEW_ANCHOR_LOOP, 1)
    elif _NEW_ANCHOR_LOOP not in card_js:
        raise RuntimeError("activity_anchor_loop_patch_missing")
    _browser.CARD_JS = card_js


def _patch_diagnostics() -> None:
    script = _diagnostics.LISTING_DIAGNOSTIC_JS
    if _OLD_DIAGNOSTIC_FILTER in script:
        script = script.replace(
            _OLD_DIAGNOSTIC_FILTER,
            _CONTENT_DIAGNOSTIC_FILTER,
            1,
        )
    elif _CONTENT_DIAGNOSTIC_FILTER not in script:
        raise RuntimeError("review_activity_card_filter_patch_missing")
    _diagnostics.LISTING_DIAGNOSTIC_JS = script


def apply() -> None:
    """Prefer rendered activity-card content over URL-route guessing.

    A visible anchor containing its own useful title and current date is a real
    listing-card candidate. URL route structure remains only a fallback for sites
    whose anchors do not expose complete card fields.
    """

    global _APPLIED
    if _APPLIED:
        return

    listing_url_authority.apply()
    _patch_card_js()
    _patch_diagnostics()
    _APPLIED = True


__all__ = ["apply"]
