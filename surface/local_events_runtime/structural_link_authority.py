from __future__ import annotations

from . import browser as _browser
from . import event_review_diagnostics as _diagnostics
from . import listing_url_authority

_APPLIED = False

_OLD_ANCHOR_DECLARATION = (
    '  const anchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));'
)

_CARD_FIRST_ANCHOR_DECLARATION = r'''  const allAnchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));

  // Use a verified source-specific card boundary when the official listing has
  // one. Gardens by the Bay renders each activity as one repeated anchor; this
  // selector intentionally excludes header, footer, ticketing, and navigation
  // links from Event candidate discovery.
  const sourceCardSelectors = {
    gardensbythebay: ["a.programme-title.row-listing-title[href]"]
  };
  const configuredSelectors = sourceCardSelectors[String(sourceId || "").toLowerCase()] || [];
  const configuredCardAnchors = [...new Set(configuredSelectors.flatMap(selector => {
    try { return Array.from(document.querySelectorAll(selector)); } catch { return []; }
  }))].filter(anchor => visible(anchor));

  // For sources without an explicit selector, locate repeated rendered activity
  // cards before considering their links. A listing page may contain dozens of
  // official-domain navigation links, while real activity cards repeat one
  // semantic anchor structure.
  const cardAnchorSignature = anchor => {
    const classes = Array.from(anchor.classList || [])
      .map(value => String(value || "").toLowerCase())
      .filter(value => /(^|[-_])(card|tile|item|event|programme|program|exhibition|activity|listing|result)([-_]|$)/.test(value))
      .sort();
    if (!classes.length) return "";
    const rect = anchor.getBoundingClientRect();
    if (rect.width < 80 || rect.height < 30 || rect.height > 1400) return "";
    return anchor.tagName + ":" + classes.join(".");
  };

  const cardAnchorGroups = new Map();
  for (const anchor of allAnchors) {
    const signature = cardAnchorSignature(anchor);
    if (!signature) continue;
    const group = cardAnchorGroups.get(signature) || [];
    group.push(anchor);
    cardAnchorGroups.set(signature, group);
  }

  const repeatedCardAnchors = [];
  for (const group of cardAnchorGroups.values()) {
    if (group.length < 2) continue;
    repeatedCardAnchors.push(...group);
  }

  const anchors = configuredCardAnchors.length
    ? configuredCardAnchors
    : (repeatedCardAnchors.length ? repeatedCardAnchors : allAnchors);'''

_OLD_DIAGNOSTIC_FILTER = (
    '  const detailAnchors = sameDomainAnchors.filter(anchor => '
    'pathRole(anchor.getAttribute("href") || "") === "detail");'
)

_CARD_FIRST_DIAGNOSTIC_FILTER = r'''  const configuredCardAnchors = /(^|\.)gardensbythebay\.com\.sg$/i.test(location.hostname)
    ? Array.from(document.querySelectorAll("a.programme-title.row-listing-title[href]")).filter(visible)
    : [];

  const cardAnchorSignature = anchor => {
    const classes = Array.from(anchor.classList || [])
      .map(value => String(value || "").toLowerCase())
      .filter(value => /(^|[-_])(card|tile|item|event|programme|program|exhibition|activity|listing|result)([-_]|$)/.test(value))
      .sort();
    if (!classes.length) return "";
    const rect = anchor.getBoundingClientRect();
    if (rect.width < 80 || rect.height < 30 || rect.height > 1400) return "";
    return anchor.tagName + ":" + classes.join(".");
  };
  const cardAnchorGroups = new Map();
  for (const anchor of sameDomainAnchors) {
    const signature = cardAnchorSignature(anchor);
    if (!signature) continue;
    const group = cardAnchorGroups.get(signature) || [];
    group.push(anchor);
    cardAnchorGroups.set(signature, group);
  }
  const repeatedCardAnchors = [];
  for (const group of cardAnchorGroups.values()) {
    if (group.length < 2) continue;
    repeatedCardAnchors.push(...group);
  }

  const listingUrl = new URL(location.href);
  const cleanPath = value => decodeURIComponent(String(value || "")).replace(/\/+$/, "");
  const listingPath = cleanPath(listingUrl.pathname);
  const listingStem = listingPath.replace(/\.html?$/i, "");
  const routeDetailAnchors = sameDomainAnchors.filter(anchor => {
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
  });

  const detailAnchors = configuredCardAnchors.length
    ? configuredCardAnchors
    : (repeatedCardAnchors.length ? repeatedCardAnchors : routeDetailAnchors);'''


def _patch_card_locator() -> None:
    card_js = _browser.CARD_JS
    if _OLD_ANCHOR_DECLARATION in card_js:
        card_js = card_js.replace(
            _OLD_ANCHOR_DECLARATION,
            _CARD_FIRST_ANCHOR_DECLARATION,
            1,
        )
    elif _CARD_FIRST_ANCHOR_DECLARATION not in card_js:
        raise RuntimeError("activity_card_anchor_declaration_missing")
    _browser.CARD_JS = card_js


def _patch_diagnostics() -> None:
    script = _diagnostics.LISTING_DIAGNOSTIC_JS
    if _OLD_DIAGNOSTIC_FILTER in script:
        script = script.replace(
            _OLD_DIAGNOSTIC_FILTER,
            _CARD_FIRST_DIAGNOSTIC_FILTER,
            1,
        )
    elif _CARD_FIRST_DIAGNOSTIC_FILTER not in script:
        raise RuntimeError("activity_card_diagnostic_filter_missing")
    _diagnostics.LISTING_DIAGNOSTIC_JS = script


def apply() -> None:
    """Locate official activity cards first, then read one link from each card."""

    global _APPLIED
    if _APPLIED:
        return

    listing_url_authority.apply()
    _patch_card_locator()
    _patch_diagnostics()
    _APPLIED = True


__all__ = ["apply"]
