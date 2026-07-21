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
    if (!sameDomain(target.href)) return false;

    const cleanPath = value => decodeURIComponent(String(value || "")).replace(/\/+$/, "");
    const targetPath = cleanPath(target.pathname);
    const listingPath = cleanPath(listing.pathname);
    if (!targetPath || targetPath === listingPath) return false;
    if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$/i.test(targetPath)) return false;

    // Preserve the extractor's existing positive route recognition. This covers
    // normal /events/<slug>, /whats-on/<slug>, etc. paths without admitting
    // unrelated navigation links from the same official domain.
    const role = typeof pathRole === "function" ? pathRole(target.href) : "other";
    if (role === "listing") return false;
    if (role === "detail") return true;

    // Some valid listing documents are files whose detail pages live below the
    // file stem, for example:
    //   /calendar-of-events.html
    //   /calendar-of-events/orchid-extravaganza-2026.html
    const listingStem = listingPath.replace(/\.html?$/i, "");
    return Boolean(listingStem && targetPath.startsWith(listingStem + "/"));
  }
'''


def _replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"listing_url_authority_patch_missing:{label}")
    return text.replace(old, new)


def apply() -> None:
    """Accept official detail URLs without turning every same-domain link into an Event.

    Existing positive detail-route recognition remains authoritative. A structural
    fallback is only allowed when a detail URL is below the current listing file's
    path stem, such as ``calendar-of-events/<event>.html``.
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
