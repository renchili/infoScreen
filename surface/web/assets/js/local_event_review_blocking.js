"use strict";

(() => {
  const labels = {
    "/api/local-events/review/discover-listings": "Collecting institution list pages",
    "/api/local-events/review/collect-events": "Collecting events and reading detail pages",
    "/api/local-events/review/open-feedback": "Saving or opening Event feedback",
  };

  function ensureOverlay() {
    let overlay = document.getElementById("review-blocking-overlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "review-blocking-overlay";
    overlay.className = "review-blocking-overlay";
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="review-blocking-dialog" role="status" aria-live="assertive" aria-busy="true">
        <div class="review-spinner" aria-hidden="true"></div>
        <div id="review-blocking-title" class="review-blocking-title">Working</div>
        <div id="review-blocking-detail" class="review-blocking-detail">Do not close or reload this page.</div>
        <div class="review-blocking-elapsed"><span id="review-blocking-seconds">0</span>s</div>
      </div>`;
    document.body.appendChild(overlay);
    return overlay;
  }

  let activeRequests = 0;
  let startedAt = 0;
  let timer = null;

  function show(message) {
    const overlay = ensureOverlay();
    activeRequests += 1;
    if (activeRequests > 1) return;

    startedAt = Date.now();
    overlay.hidden = false;
    document.documentElement.classList.add("review-is-blocked");
    document.getElementById("review-blocking-title").textContent = message || "Working";
    document.getElementById("review-blocking-seconds").textContent = "0";
    timer = window.setInterval(() => {
      const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
      const node = document.getElementById("review-blocking-seconds");
      if (node) node.textContent = String(seconds);
    }, 250);
  }

  function hide() {
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests > 0) return;

    if (timer) window.clearInterval(timer);
    timer = null;
    const overlay = ensureOverlay();
    overlay.hidden = true;
    document.documentElement.classList.remove("review-is-blocked");
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const raw = typeof input === "string" ? input : input?.url || "";
    const path = new URL(raw, window.location.href).pathname;
    const method = String(init.method || (typeof input !== "string" ? input?.method : "GET") || "GET").toUpperCase();
    const message = method === "POST" ? labels[path] : null;

    if (!message) return originalFetch(input, init);

    show(message);
    try {
      return await originalFetch(input, init);
    } finally {
      hide();
    }
  };
})();
