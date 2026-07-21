"use strict";

(() => {
  const ENDPOINT = "/api/local-events/review/listing-page";

  const byId = (id) => document.getElementById(id);
  const text = (value) => String(value || "").trim();

  function setStatus(message, kind = "") {
    const node = byId("manual-listing-status");
    if (!node) return;
    node.textContent = message;
    node.className = `status ${kind}`.trim();
  }

  async function addListingPage() {
    const sourceId = window.InfoScreenReviewContext?.selectedSourceId?.() || "";
    const input = byId("manual-listing-url");
    const button = byId("add-listing-page");
    const url = text(input?.value);

    if (!sourceId) {
      setStatus("SELECT ONE GLOBAL INSTITUTION", "error");
      byId("review-filter-source")?.focus();
      return;
    }
    if (!url) {
      setStatus("ENTER AN OFFICIAL EVENT LIST PAGE URL", "error");
      input?.focus();
      return;
    }

    button.disabled = true;
    setStatus("SAVING LIST PAGE", "warn");
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: sourceId, url }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
      }

      input.value = "";
      setStatus("LIST PAGE ADDED AS UNREVIEWED", "ok");
      document.dispatchEvent(new CustomEvent("infoscreen:review-state", {
        detail: payload,
      }));
      byId("reload-state")?.click();
    } catch (error) {
      setStatus(text(error?.message || error), "error");
    } finally {
      button.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const button = byId("add-listing-page");
    const input = byId("manual-listing-url");
    button?.addEventListener("click", addListingPage);
    input?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addListingPage();
      }
    });
    document.addEventListener("infoscreen:review-source-change", () => {
      setStatus("READY");
    });
  });
})();
