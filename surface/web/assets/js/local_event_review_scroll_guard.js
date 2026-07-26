"use strict";

(() => {
  const REVIEW_STATE_PATH = "/api/local-events/review/state";
  const RENDERING_POST_PATHS = new Set([
    "/api/local-events/review/discover-listings",
    "/api/local-events/review/collect-events",
    "/api/local-events/review/preview-events",
    "/api/local-events/review/listing-decision",
    "/api/local-events/review/event-decision",
    "/api/local-events/review/listing-page",
  ]);

  let pendingCard = null;
  let pendingScrollY = null;
  let restoreFrame = 0;
  let restoreTimer = 0;
  let resumeInFlight = false;

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
    const candidateId = String(card.dataset.candidateId || "").trim();
    if (candidateId) return `candidate:${candidateId}`;

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
            const cards = visibleCards(container);
            let target = cards.find((card) => cardKey(card) === saved.key);
            if (!target && cards.length) {
              target = cards[Math.min(saved.visibleIndex, cards.length - 1)];
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

  async function refreshAfterReturning() {
    if (
      resumeInFlight
      || document.hidden
      || document.documentElement.classList.contains("review-is-blocked")
      || document.documentElement.classList.contains("review-sequence-busy")
    ) {
      return;
    }

    const loadState = window.InfoScreenReviewStudio?.loadState;
    if (typeof loadState !== "function") return;

    resumeInFlight = true;
    rememberScroll();
    try {
      await loadState();
    } catch {
      restorePosition();
    } finally {
      resumeInFlight = false;
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
        "#collect-listings, #collect-events, #reload-state, #add-listing-page",
      );
      if (globalButton) rememberScroll();
    },
    true,
  );

  document.addEventListener("infoscreen:review-rendered", restorePosition);
})();
