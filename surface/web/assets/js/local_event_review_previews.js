"use strict";

(() => {
  const text = (value) => String(value || "").trim();

  async function request(path, options = {}) {
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

  function listingUrl(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      if (!row.textContent.trim().startsWith("URL:")) continue;
      return text(row.querySelector("code")?.textContent || row.textContent.replace(/^URL:\s*/, ""));
    }
    return "";
  }

  function eventRowsFor(url) {
    return [...document.querySelectorAll("#event-candidates > .card")].filter((card) => {
      for (const row of card.querySelectorAll(".meta > div")) {
        if (!row.textContent.trim().startsWith("Listing page:")) continue;
        const value = text(row.querySelector("code")?.textContent || row.textContent.replace(/^Listing page:\s*/, ""));
        return value === url;
      }
      return false;
    });
  }

  function previewSummary(card, url) {
    let box = card.querySelector(".listing-event-preview");
    if (!box) {
      box = document.createElement("div");
      box.className = "listing-event-preview";
      card.querySelector(".actions")?.before(box);
    }

    const rows = eventRowsFor(url);
    if (!rows.length) {
      box.innerHTML = '<strong>Event preview:</strong> not collected yet';
      return;
    }

    const titles = rows
      .map((row) => text(row.querySelector(".card-head h3")?.textContent))
      .filter(Boolean)
      .slice(0, 8);
    const warning = rows.length < 2
      ? '<div class="preview-warning">Only one Event candidate was found. This may be a detail page rather than a list page.</div>'
      : "";
    box.innerHTML = `
      <strong>Event preview: ${rows.length}</strong>
      ${warning}
      <ol>${titles.map((title) => `<li></li>`).join("")}</ol>`;
    [...box.querySelectorAll("li")].forEach((node, index) => {
      node.textContent = titles[index];
    });
  }

  async function collectPreview(card, button) {
    const url = listingUrl(card);
    if (!url) return;

    button.disabled = true;
    button.textContent = "COLLECTING PREVIEW...";
    try {
      const state = await request("/api/local-events/review/state");
      const listing = (state.listing_pages || []).find((row) => row.url === url);
      if (!listing) throw new Error("Listing page is not present in review state");

      const originalDecision = listing.decision || "pending";
      if (originalDecision !== "confirmed") {
        await request("/api/local-events/review/listing-decision", {
          method: "POST",
          body: JSON.stringify({
            candidate_id: listing.candidate_id,
            decision: "confirmed",
          }),
        });
      }

      try {
        await request("/api/local-events/review/collect-events", {
          method: "POST",
          body: "{}",
        });
      } finally {
        if (originalDecision !== "confirmed") {
          await request("/api/local-events/review/listing-decision", {
            method: "POST",
            body: JSON.stringify({
              candidate_id: listing.candidate_id,
              decision: originalDecision,
            }),
          });
        }
      }

      document.getElementById("reload-state")?.click();
    } catch (error) {
      const status = document.getElementById("global-status");
      if (status) {
        status.textContent = text(error.message || error);
        status.className = "status error";
      }
    } finally {
      button.disabled = false;
      button.textContent = "PREVIEW EVENTS";
    }
  }

  function enhanceListingCards() {
    for (const card of document.querySelectorAll("#listing-pages > .card")) {
      const url = listingUrl(card);
      if (!url) continue;
      previewSummary(card, url);

      const actions = card.querySelector(".actions");
      if (!actions || actions.querySelector(".preview-events-button")) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button small warning preview-events-button";
      button.textContent = "PREVIEW EVENTS";
      button.addEventListener("click", () => collectPreview(card, button));
      actions.prepend(button);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    enhanceListingCards();
    const listing = document.getElementById("listing-pages");
    const events = document.getElementById("event-candidates");
    const observer = new MutationObserver(enhanceListingCards);
    if (listing) observer.observe(listing, { childList: true });
    if (events) observer.observe(events, { childList: true });
  });
})();
