from __future__ import annotations

import json
from pathlib import Path

from . import browser as _browser
from . import event_review_diagnostics as _diagnostics
from . import listing_url_authority

_APPLIED = False
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "conf" / "event_sources.json"

_OLD_ANCHOR_DECLARATION = (
    '  const anchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));'
)


def _configured_selectors() -> dict[str, list[str]]:
    """Return explicit activity-card selectors keyed by source id."""

    payload = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    output: dict[str, list[str]] = {}
    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "").strip().lower()
        selectors = [
            str(value).strip()
            for value in source.get("card_selectors") or []
            if str(value).strip()
        ]
        if source_id and selectors:
            output[source_id] = selectors
    return output


def _card_first_anchor_declaration() -> str:
    selector_map = json.dumps(_configured_selectors(), ensure_ascii=False, sort_keys=True)
    return rf'''  const allAnchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));

  // Source-specific selectors are configuration, not Event enumeration. They define
  // the repeated official card boundary for sites whose anchors use generic classes
  // such as "learn-more" or whose page also contains many unrelated repeated links.
  const sourceCardSelectors = {selector_map};
  const configuredSelectors = sourceCardSelectors[String(sourceId || "").toLowerCase()] || [];
  const configuredCardAnchors = [...new Set(configuredSelectors.flatMap(selector => {{
    try {{ return Array.from(document.querySelectorAll(selector)); }} catch {{ return []; }}
  }}))].filter(anchor => visible(anchor));

  // For sources without an explicit selector, locate repeated rendered activity
  // cards before considering their links. A listing page may contain dozens of
  // official-domain navigation links, while real activity cards repeat one
  // semantic anchor structure.
  const cardAnchorSignature = anchor => {{
    const classes = Array.from(anchor.classList || [])
      .map(value => String(value || "").toLowerCase())
      .filter(value => /(^|[-_])(card|tile|item|event|programme|program|exhibition|activity|listing|result)([-_]|$)/.test(value))
      .sort();
    if (!classes.length) return "";
    const rect = anchor.getBoundingClientRect();
    if (rect.width < 80 || rect.height < 30 || rect.height > 1400) return "";
    return anchor.tagName + ":" + classes.join(".");
  }};

  const cardAnchorGroups = new Map();
  for (const anchor of allAnchors) {{
    const signature = cardAnchorSignature(anchor);
    if (!signature) continue;
    const group = cardAnchorGroups.get(signature) || [];
    group.push(anchor);
    cardAnchorGroups.set(signature, group);
  }}

  const repeatedCardAnchors = [];
  for (const group of cardAnchorGroups.values()) {{
    if (group.length < 2) continue;
    repeatedCardAnchors.push(...group);
  }}

  const anchors = configuredCardAnchors.length
    ? configuredCardAnchors
    : (repeatedCardAnchors.length ? repeatedCardAnchors : allAnchors);'''


_OLD_DIAGNOSTIC_FILTER = (
    '  const detailAnchors = sameDomainAnchors.filter(anchor => '
    'pathRole(anchor.getAttribute("href") || "") === "detail");'
)

_CARD_FIRST_DIAGNOSTIC_FILTER = r'''  const cardAnchorSignature = anchor => {
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

  const detailAnchors = repeatedCardAnchors.length ? repeatedCardAnchors : routeDetailAnchors;'''


def _patch_card_locator() -> None:
    card_js = _browser.CARD_JS
    declaration = _card_first_anchor_declaration()
    if _OLD_ANCHOR_DECLARATION in card_js:
        card_js = card_js.replace(
            _OLD_ANCHOR_DECLARATION,
            declaration,
            1,
        )
    elif "const sourceCardSelectors =" not in card_js:
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
    """Locate official activity cards first, then read one allowed official link."""

    global _APPLIED
    if _APPLIED:
        return

    listing_url_authority.apply()
    _patch_card_locator()
    _patch_diagnostics()
    _APPLIED = True


__all__ = ["apply", "_configured_selectors"]
