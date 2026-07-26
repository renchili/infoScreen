from __future__ import annotations

from . import browser as _browser

_APPLIED = False

# Dynamic official listings often render only the first batch, then append more
# cards after a "Load more" control is clicked. The expansion loop must never treat
# ordinary activity links such as "View More" as pagination controls: clicking one
# destroys the current Playwright execution context by navigating to a detail page.
#
# Stability is measured only from activity-detail URLs and activity-card counts.
# Site-wide clocks, carousels, analytics widgets, and changing shell text must not
# keep Review Studio waiting through the full collection ceiling when no activity
# inventory is changing.
DYNAMIC_LISTING_PREPARE_JS = r"""
async (args) => {
  const maxRounds = Math.max(Number(args.maxRounds || 0), 1);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();

  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 20 && rect.height >= 16;
  };
  const disabled = element => element.disabled ||
    element.getAttribute("aria-disabled") === "true" ||
    /\b(disabled|is-disabled)\b/i.test(clean(element.className));
  const label = element => clean([
    element.innerText,
    element.textContent,
    element.value,
    element.getAttribute("aria-label"),
    element.getAttribute("title")
  ].join(" "));
  const marker = element => clean([
    element.id,
    element.className,
    element.getAttribute("data-testid"),
    element.getAttribute("data-test"),
    element.getAttribute("data-action"),
    element.getAttribute("data-load-more")
  ].join(" ")).toLowerCase();
  const loadMoreLabel = value => /^(?:load more|show more|more events?|more programmes?|more programs?)\s*(?:\+|›|»|→)?$/i.test(clean(value));
  const explicitLoadMoreMarker = element => /(?:^|[\s_-])(?:load|show)[\s_-]*more(?:$|[\s_-])/i.test(marker(element));

  const safeAnchor = anchor => {
    const href = clean(anchor.getAttribute("href"));
    if (!href || href === "#" || /^javascript:/i.test(href)) return true;
    let target;
    let current;
    try {
      target = new URL(href, location.href);
      current = new URL(location.href);
    } catch {
      return false;
    }
    // A load-more anchor may update the current listing query or fragment. It may
    // not change origin or path, which would be a detail/listing navigation.
    return target.origin === current.origin && target.pathname === current.pathname;
  };

  const safeControl = element => {
    const textMatches = loadMoreLabel(label(element));
    const markerMatches = explicitLoadMoreMarker(element);
    if (!textMatches && !markerMatches) return false;

    const enclosingAnchor = element.closest("a[href]");
    if (enclosingAnchor && !safeAnchor(enclosingAnchor)) return false;
    if (element.matches("a[href]") && !safeAnchor(element)) return false;

    // Generic links are never admitted merely because their label says "more".
    // An anchor must also carry an explicit load-more marker or stay on the exact
    // listing path through a query/fragment update.
    if (element.matches("a[href]") && !markerMatches) {
      const href = clean(element.getAttribute("href"));
      if (!href || href === "#" || /^javascript:/i.test(href)) return true;
      return safeAnchor(element);
    }
    return true;
  };

  const controls = () => Array.from(document.querySelectorAll(
    "button, [role='button'], input[type='button'], input[type='submit'], " +
    "a[class*='load-more' i], a[class*='loadmore' i], " +
    "[class*='load-more' i], [class*='loadmore' i], " +
    "[data-testid*='load-more' i], [data-action*='load-more' i]"
  )).filter(visible).filter(element => !disabled(element)).filter(safeControl);

  const detailRole = raw => {
    let url;
    try { url = new URL(raw, location.href); } catch { return false; }
    if (url.origin !== location.origin) return false;
    const path = decodeURIComponent(url.pathname.toLowerCase()).replace(/\/$/, "");
    const parts = path.split("/").filter(Boolean);
    const leaf = (parts[parts.length - 1] || "").replace(/\.html$/, "");
    const generic = new Set([
      "", "whats-on", "whatson", "overview", "view-all", "events", "event",
      "exhibition", "exhibitions", "programme", "programmes", "program", "programs",
      "activities", "activity", "guided-tours"
    ]);
    if (generic.has(leaf)) return false;
    return /\/(whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|guided-tours)\//i.test(path + "/");
  };

  const activityState = () => {
    const urls = [];
    for (const anchor of document.querySelectorAll("a[href]")) {
      const raw = anchor.getAttribute("href");
      if (!detailRole(raw)) continue;
      try {
        const url = new URL(raw, location.href);
        url.hash = "";
        if (!urls.includes(url.href)) urls.push(url.href);
      } catch {}
    }
    urls.sort();

    const cardCount = Array.from(document.querySelectorAll(
      "article,li,[class*='card' i],[class*='event' i],[class*='programme' i]," +
      "[class*='program' i],[class*='exhibition' i],[class*='listing' i]"
    )).filter(visible).filter(element =>
      Array.from(element.querySelectorAll("a[href]")).some(anchor =>
        detailRole(anchor.getAttribute("href"))
      )
    ).length;

    return {signature: `${urls.join("\n")}\n#cards=${cardCount}`, urlCount: urls.length, cardCount};
  };

  let clicks = 0;
  let rounds = 0;
  let stableRounds = 0;
  let failedClicks = 0;
  let previous = activityState();

  for (let round = 0; round < maxRounds; round += 1) {
    rounds = round + 1;
    window.scrollTo(0, document.body ? document.body.scrollHeight : 0);
    await sleep(700);

    const candidates = controls().sort((left, right) =>
      right.getBoundingClientRect().top - left.getBoundingClientRect().top
    );
    let changedAfterClick = false;
    if (candidates.length) {
      const control = candidates[0];
      const before = activityState();
      const beforeUrl = location.href;
      try {
        control.scrollIntoView({block: "center"});
        await sleep(150);
        control.click();
        clicks += 1;
        for (let poll = 0; poll < 20; poll += 1) {
          await sleep(500);
          // A real in-page expansion must not navigate. Stop before attempting any
          // further DOM work if a site unexpectedly changed the URL.
          if (location.href !== beforeUrl) {
            return {
              clicks,
              rounds,
              stableRounds,
              failedClicks,
              navigationDetected: true,
              finalUrl: location.href
            };
          }
          if (activityState().signature !== before.signature) {
            changedAfterClick = true;
            break;
          }
        }
        failedClicks = changedAfterClick ? 0 : failedClicks + 1;
      } catch (error) {
        failedClicks += 1;
      }
    } else {
      // Allow ordinary lazy rendering to append activity cards, but do not let
      // unrelated shell mutations keep this loop alive for the 80-round ceiling.
      await sleep(350);
    }

    const current = activityState();
    stableRounds = current.signature === previous.signature ? stableRounds + 1 : 0;
    previous = current;

    if (!candidates.length && stableRounds >= 5) break;
    if (candidates.length && failedClicks >= 4 && stableRounds >= 4) break;
  }

  window.scrollTo(0, 0);
  await sleep(300);
  const finalState = activityState();
  return {
    clicks,
    rounds,
    stableRounds,
    failedClicks,
    navigationDetected: false,
    finalState: finalState.signature,
    activityUrlCount: finalState.urlCount,
    activityCardCount: finalState.cardCount,
    remainingControls: controls().length,
    height: document.body ? document.body.scrollHeight : 0
  };
}
"""


def apply() -> None:
    """Install complete asynchronous listing expansion for collector and Studio."""

    global _APPLIED
    if _APPLIED:
        return

    from .review_collection_scope_authority import (
        apply as apply_review_collection_scope,
    )

    apply_review_collection_scope()
    _browser.PREPARE_PAGE_JS = DYNAMIC_LISTING_PREPARE_JS
    _APPLIED = True


__all__ = ["DYNAMIC_LISTING_PREPARE_JS", "apply"]
