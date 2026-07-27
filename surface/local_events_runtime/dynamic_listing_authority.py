from __future__ import annotations

from . import browser as _browser

_APPLIED = False

# The upper round budget remains a completeness ceiling. Early completion is based
# only on listing-card/link/control state, so unrelated animations, clocks, consent
# text, and rotating banners cannot keep one institution busy for the full 80 rounds.
DYNAMIC_LISTING_PREPARE_JS = r"""
async (args) => {
  const maxRounds = Math.max(0, Number(args.maxRounds || 0));
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
    return target.origin === current.origin && target.pathname === current.pathname;
  };

  const safeControl = element => {
    const textMatches = loadMoreLabel(label(element));
    const markerMatches = explicitLoadMoreMarker(element);
    if (!textMatches && !markerMatches) return false;

    const enclosingAnchor = element.closest("a[href]");
    if (enclosingAnchor && !safeAnchor(enclosingAnchor)) return false;
    if (element.matches("a[href]") && !safeAnchor(element)) return false;

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

  const listingState = () => {
    const root = document.querySelector("main") ||
      document.querySelector("article") || document.body;
    const hrefs = new Set(
      Array.from(root ? root.querySelectorAll("a[href]") : [])
        .map(anchor => {
          try { return new URL(anchor.getAttribute("href"), location.href).href; }
          catch (error) { return ""; }
        })
        .filter(Boolean)
    );
    const cards = root ? root.querySelectorAll(
      "article, [data-infoscreen-card-id], " +
      "[class*='event-card' i], [class*='listing-card' i], " +
      "[class*='programme-card' i], [class*='activity-card' i]"
    ).length : 0;
    return [hrefs.size, cards, controls().length].join(":");
  };

  let clicks = 0;
  let rounds = 0;
  let stableRounds = 0;
  let failedClicks = 0;
  let previous = listingState();

  for (let round = 0; round < maxRounds; round += 1) {
    rounds = round + 1;
    window.scrollTo(0, document.body ? document.body.scrollHeight : 0);
    await sleep(450);

    const candidates = controls().sort((left, right) =>
      right.getBoundingClientRect().top - left.getBoundingClientRect().top
    );
    let changedAfterClick = false;
    if (candidates.length) {
      const control = candidates[0];
      const before = listingState();
      const beforeUrl = location.href;
      try {
        control.scrollIntoView({block: "center"});
        await sleep(100);
        control.click();
        clicks += 1;
        for (let poll = 0; poll < 20; poll += 1) {
          await sleep(500);
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
          if (listingState() !== before) {
            changedAfterClick = true;
            break;
          }
        }
        failedClicks = changedAfterClick ? 0 : failedClicks + 1;
      } catch (error) {
        failedClicks += 1;
      }
    } else {
      // Give intersection observers one bounded chance to append cards after scroll.
      await sleep(450);
    }

    const current = listingState();
    stableRounds = current === previous ? stableRounds + 1 : 0;
    previous = current;

    // Two unchanged listing states are enough. Dynamic non-listing text is excluded
    // from listingState, so rotating banners no longer consume the whole round budget.
    if (!candidates.length && stableRounds >= 2) break;
    if (candidates.length && failedClicks >= 3 && stableRounds >= 2) break;
  }

  window.scrollTo(0, 0);
  await sleep(150);
  return {
    clicks,
    rounds,
    stableRounds,
    failedClicks,
    navigationDetected: false,
    finalState: listingState(),
    remainingControls: controls().length,
    height: document.body ? document.body.scrollHeight : 0
  };
}
"""


def apply() -> None:
    """Install adaptive complete listing expansion for collector and Studio."""

    global _APPLIED
    if _APPLIED:
        return
    _browser.PREPARE_PAGE_JS = DYNAMIC_LISTING_PREPARE_JS
    _APPLIED = True


__all__ = ["DYNAMIC_LISTING_PREPARE_JS", "apply"]
