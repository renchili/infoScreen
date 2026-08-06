"use strict";

(() => {
  const STORAGE_KEY = "infoscreen.review.active-preview-panel";
  const SNAPSHOT_VERSION = 7;
  const text = (value) => String(value || "").trim();

  function canonical(value) {
    try {
      const url = new URL(value, window.location.href);
      url.hash = "";
      if (url.pathname !== "/") url.pathname = url.pathname.replace(/\/$/, "");
      return url.href;
    } catch {
      return text(value);
    }
  }

  function listingUrl(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      if (!text(row.textContent).startsWith("URL:")) continue;
      return text(
        row.querySelector("code")?.textContent
        || row.textContent.replace(/^URL:\s*/, ""),
      );
    }
    return "";
  }

  function listingStillExists(url) {
    const expected = canonical(url);
    return [...document.querySelectorAll("#listing-pages > .card")]
      .some((card) => canonical(listingUrl(card)) === expected);
  }

  function readStored() {
    try {
      const value = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
      return value && typeof value === "object" ? value : null;
    } catch {
      return null;
    }
  }

  function clearStored() {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // A disabled storage backend must not break the Review Studio.
    }
  }

  function capture(url) {
    const container = document.getElementById("event-candidates");
    const count = document.getElementById("event-count");
    const title = document.getElementById("event-candidates-title");
    const hint = document.getElementById("event-candidates-hint");
    if (!container || !count || !url) return;

    const hasPreviewContent = Boolean(
      container.querySelector('[data-preview="true"]')
      || container.querySelector(".empty"),
    );
    if (!hasPreviewContent) return;

    const snapshot = {
      version: SNAPSHOT_VERSION,
      url: canonical(url),
      captured_at: new Date().toISOString(),
      title: text(title?.textContent) || "Preview event candidates",
      hint: text(hint?.textContent),
      count: text(count.textContent) || "0",
    };

    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      // Preview remains visible for the current render if storage is unavailable.
    }
  }

  function validateAfterRender() {
    const snapshot = readStored();
    if (!snapshot || snapshot.version !== SNAPSHOT_VERSION || !text(snapshot.url)) {
      if (snapshot) clearStored();
      return false;
    }
    if (!listingStillExists(snapshot.url)) {
      clearStored();
      return false;
    }

    // The active record contains identity and panel metadata only. The Preview owner
    // rebuilds the panel from its versioned structured candidate snapshot after the
    // server-state render; no parser-produced HTML is stored or restored.
    return true;
  }

  document.addEventListener("infoscreen:review-preview", (event) => {
    if (event.detail?.restored) return;
    const url = text(event.detail?.url);
    if (url) capture(url);
  });

  document.addEventListener("infoscreen:review-rendered", validateAfterRender);

  document.addEventListener("infoscreen:review-state", () => {
    // This event is emitted only by formal Event collection. Persisted candidates
    // supersede the temporary active Preview panel.
    clearStored();
  });
})();
