from __future__ import annotations

from . import browser as _browser

_APPLIED = False

# A listing page may contain carousels, step indicators, level numbers, and unrelated
# controls whose visible text is merely "2" or "Next". The old paginator accepted
# those controls and incremented page_index even when the Event inventory had not
# changed. Review then re-read the same six ACM cards as a second page and opened a
# second batch of detail tabs. A pagination transition is valid only when the listing
# URL or the canonical set of activity-detail URLs actually changes.
VALIDATED_NEXT_PAGE_JS = r"""
async (args) => {
  const allowedDomains = (args.allowedDomains || [])
    .map(value => String(value || "").replace(/^www\./, "").toLowerCase());
  const pageIndex = Number(args.pageIndex || 0);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();

  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 18 && rect.height >= 16;
  };
  const disabled = element => element.disabled ||
    element.getAttribute("aria-disabled") === "true" ||
    /\b(disabled|is-disabled)\b/i.test(clean(element.className));
  const canonical = raw => {
    try {
      const url = new URL(raw, location.href);
      url.hash = "";
      return url.href;
    } catch {
      return "";
    }
  };
  const sameDomain = raw => {
    try {
      const host = new URL(raw, location.href).hostname
        .replace(/^www\./, "").toLowerCase();
      return allowedDomains.some(domain => host === domain || host.endsWith("." + domain));
    } catch {
      return false;
    }
  };
  const pathRole = raw => {
    let url;
    try { url = new URL(raw, location.href); } catch { return "other"; }
    const path = decodeURIComponent(url.pathname.toLowerCase()).replace(/\/$/, "");
    const parts = path.split("/").filter(Boolean);
    const leaf = (parts[parts.length - 1] || "").replace(/\.html$/, "");
    const generic = new Set([
      "", "whats-on", "whatson", "overview", "view-all", "events", "event",
      "exhibition", "exhibitions", "programme", "programmes", "program", "programs",
      "activities", "activity", "guided-tours"
    ]);
    if (/[?&](category|filter|time|date|type|page)=/i.test(url.search)) return "listing";
    if (generic.has(leaf)) return "listing";
    if (/\/(whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|guided-tours)\//i.test(path + "/")) {
      return "detail";
    }
    return "other";
  };
  const inventory = () => {
    const urls = [];
    for (const anchor of document.querySelectorAll("a[href]")) {
      const href = canonical(anchor.getAttribute("href"));
      if (!href || !sameDomain(href) || pathRole(href) !== "detail") continue;
      if (!urls.includes(href)) urls.push(href);
    }
    urls.sort();
    return urls;
  };
  const snapshot = () => ({
    pageUrl: canonical(location.href),
    detailUrls: inventory(),
  });
  const changed = (before, after) =>
    before.pageUrl !== after.pageUrl ||
    before.detailUrls.join("\n") !== after.detailUrls.join("\n");

  const controlText = element => clean([
    element.innerText,
    element.textContent,
    element.getAttribute("aria-label"),
    element.getAttribute("title")
  ].join(" "));
  const paginationContainer = element => element.closest(
    "nav[aria-label*='page' i], [role='navigation'][aria-label*='page' i], " +
    "[class*='pagination' i], [class*='pager' i], [class*='paging' i], " +
    "[id*='pagination' i], [id*='pager' i], [id*='paging' i]"
  );
  const hrefLooksPaged = element => {
    if (!element.matches("a[href]")) return false;
    const href = element.getAttribute("href") || "";
    if (!href || href === "#" || /^javascript:/i.test(href)) return false;
    try {
      const target = new URL(href, location.href);
      return sameDomain(target.href) && pathRole(target.href) !== "detail" &&
        (/[?&](page|p|offset|start)=\d+/i.test(target.search) ||
         target.pathname !== location.pathname);
    } catch {
      return false;
    }
  };
  const hasPaginationEvidence = element =>
    Boolean(paginationContainer(element)) || hrefLooksPaged(element);
  const isNextControl = element => {
    if (!visible(element) || disabled(element) || !hasPaginationEvidence(element)) return false;
    const text = controlText(element);
    if (/\b(next programme|next program|next exhibition|next event|next article)\b/i.test(text)) return false;
    return /^(next|>|›|»|→)$/i.test(text) ||
      /\b(next page|go to next page|page next|next results?)\b/i.test(text);
  };
  const isNumericNextControl = element => {
    if (!visible(element) || disabled(element) || !paginationContainer(element)) return false;
    const text = controlText(element);
    if (!/^\d+$/.test(text)) return false;
    return Number(text) === pageIndex + 2;
  };
  const score = element => {
    let value = 0;
    if (paginationContainer(element)) value += 100;
    if (hrefLooksPaged(element)) value += 60;
    if (/\b(next page|page next)\b/i.test(controlText(element))) value += 40;
    return value;
  };

  const candidates = Array.from(document.querySelectorAll("a[href], button, [role='button']"))
    .filter(element => isNextControl(element) || isNumericNextControl(element))
    .sort((left, right) => score(right) - score(left));
  if (!candidates.length) {
    return {clicked: false, changed: false, reason: "next_control_not_found"};
  }

  const control = candidates[0];
  const before = snapshot();
  const label = controlText(control);
  try {
    control.scrollIntoView({block: "center"});
    await sleep(150);
    control.click();
  } catch (error) {
    return {clicked: false, changed: false, text: label, reason: String(error)};
  }

  let after = snapshot();
  for (let poll = 0; poll < 24 && !changed(before, after); poll += 1) {
    await sleep(250);
    after = snapshot();
  }
  if (!changed(before, after)) {
    return {
      clicked: false,
      changed: false,
      text: label,
      reason: "next_control_did_not_change_listing_inventory",
      beforeUrl: before.pageUrl,
      afterUrl: after.pageUrl,
      beforeDetailCount: before.detailUrls.length,
      afterDetailCount: after.detailUrls.length,
    };
  }

  return {
    clicked: true,
    changed: true,
    text: label,
    beforeUrl: before.pageUrl,
    afterUrl: after.pageUrl,
    beforeDetailCount: before.detailUrls.length,
    afterDetailCount: after.detailUrls.length,
  };
}
"""


def apply() -> None:
    """Install inventory-validated pagination for collector and Review Studio."""

    global _APPLIED
    if _APPLIED:
        return
    _browser.CLICK_NEXT_PAGE_JS = VALIDATED_NEXT_PAGE_JS
    _APPLIED = True


__all__ = ["VALIDATED_NEXT_PAGE_JS", "apply"]
