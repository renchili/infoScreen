from __future__ import annotations

from . import browser as _browser

_APPLIED = False

# Dynamic official listings often render only the first batch, then append more
# cards after a "Load more" control is clicked. The old loop waited a fixed 850 ms
# and could declare the document stable before the asynchronous response arrived.
# This implementation waits for an observable document change after every click and
# supports button, link, role, input, and load-more container implementations.
DYNAMIC_LISTING_PREPARE_JS = r"""
async (args) => {
  const maxRounds = Math.max(Number(args.maxRounds || 0), 80);
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
  const loadMoreLabel = value => /^(?:load more|show more|view more|more events?|more programmes?|more programs?|see more)\s*(?:\+|›|»|→)?$/i.test(clean(value));
  const controls = () => Array.from(document.querySelectorAll(
    "button, a[href], [role='button'], input[type='button'], input[type='submit'], " +
    "[class*='load-more' i], [class*='loadmore' i], [data-testid*='load-more' i]"
  )).filter(visible).filter(element => !disabled(element)).filter(element => loadMoreLabel(label(element)));
  const state = () => {
    const body = document.body;
    const links = Array.from(document.querySelectorAll("a[href]"))
      .map(anchor => anchor.href).filter(Boolean);
    return [
      body ? body.scrollHeight : 0,
      clean(body ? (body.innerText || body.textContent || "") : "").length,
      new Set(links).size,
      document.querySelectorAll("article,li,[class*='card' i],[class*='event' i],[class*='listing' i]").length
    ].join(":");
  };

  let clicks = 0;
  let rounds = 0;
  let stableRounds = 0;
  let failedClicks = 0;
  let previous = state();

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
      const before = state();
      try {
        control.scrollIntoView({block: "center"});
        await sleep(150);
        control.click();
        clicks += 1;
        for (let poll = 0; poll < 20; poll += 1) {
          await sleep(500);
          if (state() !== before) {
            changedAfterClick = true;
            break;
          }
        }
        failedClicks = changedAfterClick ? 0 : failedClicks + 1;
      } catch (error) {
        failedClicks += 1;
      }
    } else {
      await sleep(900);
    }

    const current = state();
    stableRounds = current === previous ? stableRounds + 1 : 0;
    previous = current;

    if (!candidates.length && stableRounds >= 5) break;
    if (candidates.length && failedClicks >= 4 && stableRounds >= 4) break;
  }

  window.scrollTo(0, 0);
  await sleep(300);
  return {
    clicks,
    rounds,
    stableRounds,
    failedClicks,
    finalState: state(),
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
    _browser.PREPARE_PAGE_JS = DYNAMIC_LISTING_PREPARE_JS
    _APPLIED = True


__all__ = ["DYNAMIC_LISTING_PREPARE_JS", "apply"]
