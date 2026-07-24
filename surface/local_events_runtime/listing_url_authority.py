from __future__ import annotations

from . import browser as _browser

_applied = False

SAME_DOMAIN_BLOCK = r'''  function sameDomain(raw) {
    let u;
    try { u = new URL(raw, document.location.href); } catch { return false; }
    const h = u.hostname.replace(/^www\./, "").toLowerCase();
    return allowedDomains.some(d => h === String(d).replace(/^www\./, "").toLowerCase() || h.endsWith("." + String(d).replace(/^www\./, "").toLowerCase()));
  }
'''

OFFICIAL_DETAIL_HELPER = r'''
  function officialDetailUrl(raw) {
    let target;
    let listing;
    try {
      target = new URL(raw, document.location.href);
      listing = new URL(document.location.href);
    } catch {
      return false;
    }

    // The configured or operator-confirmed listing page is the official authority.
    // A link rendered inside one of its Event cards may legitimately lead to an
    // associated institution site, ticketing site, or independently hosted Event
    // page. The target therefore does not need to share the listing hostname.
    if (!/^https?:$/i.test(target.protocol)) return false;
    if (target.username || target.password) return false;

    const cleanPath = value => decodeURIComponent(String(value || "")).replace(/\/+$/, "") || "/";
    const targetPath = cleanPath(target.pathname);
    const listingPath = cleanPath(listing.pathname);
    if (
      target.origin === listing.origin &&
      targetPath === listingPath &&
      target.search === listing.search
    ) return false;
    if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$/i.test(targetPath)) return false;
    return true;
  }
'''


def _replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"listing_url_authority_patch_missing:{label}")
    return text.replace(old, new)


def apply() -> None:
    """Trust safe activity links rendered by an authoritative official listing.

    ``allowed_domains`` continues to validate listing-page provenance. It is not a
    restriction on the destination of an activity link that the confirmed listing
    itself explicitly renders.
    """

    global _applied
    if _applied:
        return

    card_js = _browser.CARD_JS
    card_js = _replace_required(
        card_js,
        SAME_DOMAIN_BLOCK,
        SAME_DOMAIN_BLOCK + OFFICIAL_DETAIL_HELPER,
        "official_detail_helper",
    )
    card_js = _replace_required(
        card_js,
        'if (sameDomain(abs) && pathRole(abs) === "detail" && !urls.includes(abs)) urls.push(abs);',
        'if (officialDetailUrl(abs) && !urls.includes(abs)) urls.push(abs);',
        "detail_url_collection",
    )
    card_js = _replace_required(
        card_js,
        '''      if (!sameDomain(abs)) continue;
      if (pathRole(abs) === "listing") continue;''',
        '''      if (!officialDetailUrl(abs)) continue;''',
        "same_domain_non_listing_collection",
    )
    card_js = _replace_required(
        card_js,
        'if (sameDomain(abs) && pathRole(abs) !== "listing") return abs;',
        'if (officialDetailUrl(abs)) return abs;',
        "structured_object_url",
    )
    card_js = _replace_required(
        card_js,
        'if (!sameDomain(abs) || pathRole(abs) !== "detail") continue;',
        'if (!officialDetailUrl(abs)) continue;',
        "listing_anchor_filter",
    )

    _browser.CARD_JS = card_js
    _applied = True


__all__ = ["apply", "OFFICIAL_DETAIL_HELPER"]
