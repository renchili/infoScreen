"use strict";

(() => {
  const STATE_PATH = "/api/local-events/review/state";
  let refreshTimer = 0;
  let lastPayload = null;

  const text = (value) => String(value || "").trim();

  function listingUrl(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      if (!text(row.textContent).startsWith("URL:")) continue;
      return text(row.querySelector("code")?.textContent || row.textContent.replace(/^URL:\s*/, ""));
    }
    return "";
  }

  function collectionError(payload, url) {
    const errors = payload?.event_collection?.errors;
    if (!Array.isArray(errors)) return "";
    const row = errors.find((item) => text(item?.listing_url) === url);
    return text(row?.error);
  }

  function zeroReason(payload, url) {
    const error = collectionError(payload, url);
    if (error) {
      return `Collection failed for this page: ${error}`;
    }

    const completedAt = text(payload?.event_collection?.completed_at);
    if (!completedAt) {
      return "No collection result exists for this page yet.";
    }

    return [
      "The page collection completed, but the collector did not recognise an isolated official Event card with a usable detail-page link.",
      "This does not mean the listing URL is wrong.",
      "A date on the listing card is not required; date and venue must be read from the official detail page after the detail link is admitted.",
    ].join(" ");
  }

  function applyDiagnostics(payload) {
    lastPayload = payload;
    for (const card of document.querySelectorAll("#listing-pages > .card")) {
      const heading = card.querySelector(".listing-event-preview-heading");
      if (!heading || text(heading.textContent) !== "EVENT PREVIEW · 0") continue;

      const url = listingUrl(card);
      if (!url) continue;

      let reason = card.querySelector(".listing-event-preview-reason");
      if (!reason) {
        reason = document.createElement("div");
        reason.className = "preview-warning listing-event-preview-reason";
        card.querySelector(".listing-event-preview")?.appendChild(reason);
      }
      reason.textContent = zeroReason(payload, url);
    }
  }

  async function loadDiagnostics() {
    try {
      const response = await fetch(STATE_PATH, { cache: "no-store" });
      const payload = await response.json();
      if (response.ok) applyDiagnostics(payload);
    } catch {
      // The main page already exposes the state request failure.
    }
  }

  function scheduleDiagnostics() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => {
      if (lastPayload) applyDiagnostics(lastPayload);
      loadDiagnostics();
    }, 80);
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadDiagnostics();
    const listing = document.getElementById("listing-pages");
    if (listing) {
      new MutationObserver(scheduleDiagnostics).observe(listing, {
        childList: true,
        subtree: true,
      });
    }
  });
})();
