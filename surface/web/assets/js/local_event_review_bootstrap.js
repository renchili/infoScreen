"use strict";

(() => {
  const INITIALIZED_KEY = "infoscreen.localEventReview.initialized";

  async function jsonRequest(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  async function initializeConfiguredListingPages() {
    try {
      const state = await jsonRequest("/api/local-events/review/state");
      if (Array.isArray(state.listing_pages) && state.listing_pages.length > 0) {
        sessionStorage.removeItem(INITIALIZED_KEY);
        return;
      }
      if (sessionStorage.getItem(INITIALIZED_KEY) === "1") return;

      sessionStorage.setItem(INITIALIZED_KEY, "1");
      const status = document.getElementById("global-status");
      if (status) {
        status.textContent = "INITIALIZING CONFIGURED LIST PAGES";
        status.className = "status warn";
      }

      await jsonRequest("/api/local-events/review/discover-listings", {
        method: "POST",
        body: "{}",
      });
      window.location.reload();
    } catch (error) {
      const status = document.getElementById("global-status");
      if (status) {
        status.textContent = String(error.message || error);
        status.className = "status error";
      }
    }
  }

  document.addEventListener("DOMContentLoaded", initializeConfiguredListingPages);
})();
