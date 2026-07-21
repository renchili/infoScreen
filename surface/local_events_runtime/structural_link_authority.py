from __future__ import annotations

from . import event_review_diagnostics as _diagnostics
from . import listing_url_authority

_APPLIED = False

_OLD_DIAGNOSTIC_FILTER = (
    '  const detailAnchors = sameDomainAnchors.filter(anchor => '
    'pathRole(anchor.getAttribute("href") || "") === "detail");'
)

_STRUCTURAL_DIAGNOSTIC_FILTER = r'''  const listingUrl = new URL(location.href);
  const cleanPath = value => decodeURIComponent(String(value || "")).replace(/\/+$/, "");
  const listingPath = cleanPath(listingUrl.pathname);
  const detailAnchors = sameDomainAnchors.filter(anchor => {
    let target;
    try {
      target = new URL(anchor.getAttribute("href") || "", location.href);
    } catch {
      return false;
    }
    const targetPath = cleanPath(target.pathname);
    if (!targetPath || targetPath === listingPath) return false;
    if (/\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$/i.test(targetPath)) return false;
    return true;
  });'''


def apply() -> None:
    """Use one structural rule for production extraction and Review diagnostics.

    An official detail link is a same-domain HTTP(S) link whose path differs from
    the current listing page and is not a media/document asset. This intentionally
    does not enumerate route words: valid sites may use paths such as
    ``calendar-of-events/<event>.html``.
    """

    global _APPLIED
    if _APPLIED:
        return

    # Patch CARD_JS so the real collector accepts structural official links.
    listing_url_authority.apply()

    # Keep the Studio's "Possible detail links" counter on the exact same rule.
    script = _diagnostics.LISTING_DIAGNOSTIC_JS
    if _OLD_DIAGNOSTIC_FILTER in script:
        script = script.replace(
            _OLD_DIAGNOSTIC_FILTER,
            _STRUCTURAL_DIAGNOSTIC_FILTER,
        )
    elif _STRUCTURAL_DIAGNOSTIC_FILTER not in script:
        raise RuntimeError("review_structural_link_filter_patch_missing")
    _diagnostics.LISTING_DIAGNOSTIC_JS = script
    _APPLIED = True


__all__ = ["apply"]
