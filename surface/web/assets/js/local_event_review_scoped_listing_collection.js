"use strict";

(() => {
  const text = (value) => String(value || "").trim();

  function setGlobalStatus(message, kind = "") {
    const status = document.getElementById("global-status");
    if (!status) return;
    status.textContent = message;
    status.className = `status ${kind}`.trim();
  }

  async function collectSelectedInstitution(button) {
    const sourceId = text(window.InfoScreenReviewContext?.selectedSourceId?.());
    const sourceName = text(
      window.InfoScreenReviewContext?.sourceName?.(sourceId) || sourceId,
    );
    if (!sourceId) {
      setGlobalStatus("SELECT ONE INSTITUTION BEFORE COLLECTING LIST PAGES", "error");
      return;
    }

    button.disabled = true;
    setGlobalStatus(`COLLECTING LIST PAGES FOR ${sourceName}`, "warn");
    try {
      const response = await fetch("/api/local-events/review/discover-listings", {
        method: "POST",
        cache: "no-store",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({source_id: sourceId}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
      }

      await window.InfoScreenReviewStudio?.loadState?.();
      const count = (payload.listing_pages || [])
        .filter((row) => text(row.source_id) === sourceId)
        .length;
      setGlobalStatus(
        `${count} LIST PAGE CANDIDATE${count === 1 ? "" : "S"} READY FOR PREVIEW · ${sourceName}`,
        count ? "ok" : "error",
      );
    } catch (error) {
      setGlobalStatus(text(error?.message || error), "error");
    } finally {
      button.disabled = false;
    }
  }

  function install() {
    const original = document.getElementById("collect-listings");
    if (!original || original.dataset.singleInstitution === "true") return;

    const button = original.cloneNode(true);
    button.dataset.singleInstitution = "true";
    button.textContent = "COLLECT LIST PAGES FOR SELECTED INSTITUTION";
    button.title = "Discover candidate list pages for the selected institution before confirmation.";
    button.addEventListener("click", () => collectSelectedInstitution(button));
    original.replaceWith(button);
  }

  document.addEventListener("DOMContentLoaded", install);
})();
