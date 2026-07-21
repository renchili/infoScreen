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
  const listingStem = listingPath.replace(/\.html?$/i, "");
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

    const role = pathRole(target.href);
    if (role === "listing") return false;
    if (role === "detail") return true;
    return Boolean(listingStem && targetPath.startsWith(listingStem + "/"));
  });'''


def apply() -> None:
    """Use the same route-scoped official-link rule in collection and diagnostics.

    Normal recognised Event routes remain accepted. The structural fallback is
    limited to descendants of a listing file stem, so a page with dozens of
    unrelated official navigation links cannot trigger dozens of detail reads.
    """

    global _APPLIED
    if _APPLIED:
        return

    listing_url_authority.apply()

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
