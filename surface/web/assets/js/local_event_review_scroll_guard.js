"use strict";

(() => {
  const REVIEW_STATE_PATH = "/api/local-events/review/state";
  const RENDERING_POST_PATHS = new Set([
    "/api/local-events/review/discover-listings",
    "/api/local-events/review/collect-events",
    "/api/local-events/review/listing-decision",
    "/api/local-events/review/event-decision",
  ]);

  let pendingCard = null;
  let pendingScrollY = null;
  let restoreFrame = 0;
  let restoreTimer = 0;
  let resumeHandler = null;

  function pathAndMethod(input, init = {}) {
    const raw = typeof input === "string" ? input : input?.url || "";
    const path = new URL(raw, window.location.href).pathname;
    const method = String(
      init.method || (typeof input !== "string" ? input?.method : "GET") || "GET",
    ).toUpperCase();
    return { path, method };
  }

  function normalizedUrl(value) {
    try {
      const url = new URL(value || "", window.location.href);
      url.hash = "";
      return url.href;
    } catch {
      return String(value || "").trim();
    }
  }

  function cardKey(card) {
    if (!card) return "";
    const primaryUrl = normalizedUrl(
      card.querySelector(".card-head a[href]")?.getAttribute("href") || "",
    );
    const listingUrl = normalizedUrl(
      card.querySelector(".meta code")?.textContent || "",
    );
    return `${primaryUrl}\n${listingUrl}`;
  }

  function visibleCards(container) {
    if (!container) return [];
    return [...container.children].filter(
      (card) => card.classList?.contains("card") && !card.hidden,
    );
  }

  function rememberCard(button) {
    const card = button?.closest(".card");
    const container = card?.parentElement;
    if (!card || !container?.id) return;

    const cards = visibleCards(container);
    pendingCard = {
      containerId: container.id,
      key: cardKey(card),
      visibleIndex: Math.max(0, cards.indexOf(card)),
      viewportTop: card.getBoundingClientRect().top,
      scrollY: window.scrollY,
    };
    pendingScrollY = null;
  }

  function rememberScroll() {
    if (pendingCard || pendingScrollY !== null) return;
    pendingScrollY = window.scrollY;
  }

  function restorePosition() {
    window.cancelAnimationFrame(restoreFrame);
    window.clearTimeout(restoreTimer);

    restoreFrame = window.requestAnimationFrame(() => {
      restoreFrame = window.requestAnimationFrame(() => {
        restoreTimer = window.setTimeout(() => {
          if (pendingCard) {
            const saved = pendingCard;
            const container = document.getElementById(saved.containerId);
            const allCards = container
              ? [...container.children].filter((card) => card.classList?.contains("card"))
              : [];
            let target = allCards.find((card) => cardKey(card) === saved.key && !card.hidden);
            if (!target) {
              const visible = visibleCards(container);
              target = visible[Math.min(saved.visibleIndex, Math.max(0, visible.length - 1))];
            }

            if (target) {
              const delta = target.getBoundingClientRect().top - saved.viewportTop;
              window.scrollTo({
                top: Math.max(0, window.scrollY + delta),
                left: 0,
                behavior: "auto",
              });
            } else {
              window.scrollTo({ top: saved.scrollY, left: 0, behavior: "auto" });
            }
            pendingCard = null;
            pendingScrollY = null;
            return;
          }

          if (pendingScrollY === null) return;
          const maxScroll = Math.max(
            0,
            document.documentElement.scrollHeight - window.innerHeight,
          );
          window.scrollTo({
            top: Math.min(pendingScrollY, maxScroll),
            left: 0,
            behavior: "auto",
          });
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
    if (Number(delay) === 3000 && typeof handler === "function") {
      resumeHandler = () => handler(...args);
      return -1;
    }
    return previousSetInterval(handler, delay, ...args);
  };

  async function refreshAfterReturning() {
    if (
      document.hidden
      || typeof resumeHandler !== "function"
      || document.documentElement.classList.contains("review-is-blocked")
      || document.documentElement.classList.contains("review-sequence-busy")
    ) {
      return;
    }

    rememberScroll();
    try {
      await resumeHandler();
    } finally {
      restorePosition();
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshAfterReturning();
  });

  document.addEventListener(
    "click",
    (event) => {
      const reviewButton = event.target.closest(
        "#listing-pages button, #event-candidates button",
      );
      if (reviewButton) {
        rememberCard(reviewButton);
        return;
      }

      const globalButton = event.target.closest(
        "#collect-listings, #collect-events, #reload-state",
      );
      if (globalButton) rememberScroll();
    },
    true,
  );

  document.addEventListener("DOMContentLoaded", () => {
    const observer = new MutationObserver(() => restorePosition());
    for (const id of ["listing-pages", "event-candidates", "feedback-list"]) {
      const node = document.getElementById(id);
      if (node) observer.observe(node, { childList: true });
    }
  });
})();
