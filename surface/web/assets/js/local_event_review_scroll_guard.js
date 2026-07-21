"use strict";

(() => {
  const REVIEW_STATE_PATH = "/api/local-events/review/state";
  const RENDERING_POST_PATHS = new Set([
    "/api/local-events/review/discover-listings",
    "/api/local-events/review/collect-events",
    "/api/local-events/review/listing-decision",
    "/api/local-events/review/event-decision",
  ]);

  let pendingScrollY = null;
  let restoreFrame = 0;
  let restoreTimer = 0;
  let restoring = false;

  function pathAndMethod(input, init = {}) {
    const raw = typeof input === "string" ? input : input?.url || "";
    const path = new URL(raw, window.location.href).pathname;
    const method = String(
      init.method || (typeof input !== "string" ? input?.method : "GET") || "GET",
    ).toUpperCase();
    return { path, method };
  }

  function rememberScroll() {
    if (pendingScrollY === null) pendingScrollY = window.scrollY;
  }

  function restoreScroll() {
    if (pendingScrollY === null) return;
    window.cancelAnimationFrame(restoreFrame);
    window.clearTimeout(restoreTimer);

    const target = pendingScrollY;
    restoreFrame = window.requestAnimationFrame(() => {
      restoreFrame = window.requestAnimationFrame(() => {
        restoreTimer = window.setTimeout(() => {
          const maxScroll = Math.max(
            0,
            document.documentElement.scrollHeight - window.innerHeight,
          );
          restoring = true;
          window.scrollTo({
            top: Math.min(target, maxScroll),
            left: 0,
            behavior: "auto",
          });
          restoring = false;
          pendingScrollY = null;
        }, 0);
      });
    });
  }

  const previousFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const { path, method } = pathAndMethod(input, init);
    if (
      (method === "GET" && path === REVIEW_STATE_PATH)
      || (method === "POST" && RENDERING_POST_PATHS.has(path))
    ) {
      rememberScroll();
    }
    return previousFetch(input, init);
  };

  const previousSetInterval = window.setInterval.bind(window);
  window.setInterval = (handler, delay, ...args) => {
    if (Number(delay) !== 3000 || typeof handler !== "function") {
      return previousSetInterval(handler, delay, ...args);
    }

    return previousSetInterval(async (...callbackArgs) => {
      if (
        document.hidden
        || document.documentElement.classList.contains("review-is-blocked")
        || document.documentElement.classList.contains("review-sequence-busy")
      ) {
        return;
      }

      rememberScroll();
      try {
        await handler(...callbackArgs);
      } finally {
        restoreScroll();
      }
    }, delay, ...args);
  };

  document.addEventListener(
    "click",
    (event) => {
      const trigger = event.target.closest(
        "#collect-listings, #collect-events, #reload-state, "
          + "#listing-pages button, #event-candidates button",
      );
      if (trigger) rememberScroll();
    },
    true,
  );

  document.addEventListener("scroll", () => {
    if (restoring) return;
  }, { passive: true });

  document.addEventListener("DOMContentLoaded", () => {
    const observer = new MutationObserver(() => restoreScroll());
    for (const id of ["listing-pages", "event-candidates", "feedback-list"]) {
      const node = document.getElementById(id);
      if (node) observer.observe(node, { childList: true });
    }
  });
})();
