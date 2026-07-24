"use strict";

(() => {
  const FILTER_SOURCE_KEY = "infoscreen.review.filter.source";
  const FILTER_STATUS_KEY = "infoscreen.review.filter.status";
  const REVIEW_STATE_PATH = "/api/local-events/review/state";

  let restoreScrollY = null;
  let restoreTimer = null;
  let sourcesById = new Map();
  let sourceIdByName = new Map();
  let syncingSource = false;

  function text(value) {
    return String(value || "").trim();
  }

  function cardStatus(card) {
    if (card.classList.contains("confirmed")) return "confirmed";
    if (card.classList.contains("rejected")) return "rejected";
    return "pending";
  }

  function allCards() {
    return [
      ...document.querySelectorAll("#listing-pages > .card"),
      ...document.querySelectorAll("#event-candidates > .card"),
    ];
  }

  function institutionNameFromMeta(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      const value = text(row.textContent);
      if (!value.startsWith("Institution:")) continue;
      return text(value.slice("Institution:".length));
    }
    return "";
  }

  function institutionNameFromListingHeading(card) {
    if (!card.matches("#listing-pages > .card")) return "";
    return text(card.querySelector(".card-head h3 a, .card-head h3")?.textContent);
  }

  function cardSourceId(card) {
    const explicit = text(card.dataset.sourceId);
    if (explicit && sourcesById.has(explicit)) return explicit;

    const institutionName = institutionNameFromMeta(card);
    if (institutionName && sourceIdByName.has(institutionName)) {
      const sourceId = sourceIdByName.get(institutionName);
      card.dataset.sourceId = sourceId;
      return sourceId;
    }

    const listingName = institutionNameFromListingHeading(card);
    if (listingName && sourceIdByName.has(listingName)) {
      const sourceId = sourceIdByName.get(listingName);
      card.dataset.sourceId = sourceId;
      return sourceId;
    }

    return "";
  }

  function selectedSourceId() {
    const sourceId = text(document.getElementById("review-filter-source")?.value);
    return sourcesById.has(sourceId) ? sourceId : "";
  }

  function sourceName(sourceId) {
    return sourcesById.get(sourceId)?.source_name || sourceId || "All institutions";
  }

  function publishSourceChange() {
    document.dispatchEvent(new CustomEvent("infoscreen:review-source-change", {
      detail: {
        sourceId: selectedSourceId(),
        sourceName: sourceName(selectedSourceId()),
      },
    }));
  }

  function syncFeedbackSource(sourceId) {
    if (!sourceId || syncingSource) return;
    const feedbackSource = document.getElementById("feedback-source");
    if (!feedbackSource) return;
    const exists = [...feedbackSource.options].some((option) => option.value === sourceId);
    if (!exists || feedbackSource.value === sourceId) return;

    syncingSource = true;
    feedbackSource.value = sourceId;
    feedbackSource.dispatchEvent(new Event("change", { bubbles: true }));
    syncingSource = false;
  }

  function setGlobalSource(sourceId, { syncFeedback = true } = {}) {
    const select = document.getElementById("review-filter-source");
    if (!select) return;

    const normalized = sourcesById.has(sourceId) ? sourceId : "";
    if (select.value !== normalized) select.value = normalized;

    if (normalized) {
      sessionStorage.setItem(FILTER_SOURCE_KEY, normalized);
    } else {
      sessionStorage.removeItem(FILTER_SOURCE_KEY);
    }

    applyFilters();
    if (syncFeedback) syncFeedbackSource(normalized);
    publishSourceChange();
  }

  function ensureFilters() {
    const toolbar = document.querySelector(".toolbar");
    if (!toolbar || document.getElementById("review-filter-source")) return;

    const group = document.createElement("div");
    group.className = "review-filters";
    group.innerHTML = `
      <label>
        <span>Global institution</span>
        <select id="review-filter-source">
          <option value="">ALL INSTITUTIONS</option>
        </select>
      </label>
      <label>
        <span>Review state</span>
        <select id="review-filter-status">
          <option value="">ALL STATES</option>
          <option value="pending">UNREVIEWED</option>
          <option value="reviewed">REVIEWED</option>
          <option value="confirmed">CONFIRMED</option>
          <option value="rejected">REJECTED</option>
        </select>
      </label>`;
    toolbar.appendChild(group);

    const source = document.getElementById("review-filter-source");
    const status = document.getElementById("review-filter-status");
    status.value = sessionStorage.getItem(FILTER_STATUS_KEY) || "";

    source.addEventListener("change", () => {
      setGlobalSource(source.value);
    });
    status.addEventListener("change", () => {
      sessionStorage.setItem(FILTER_STATUS_KEY, status.value);
      applyFilters();
    });
  }

  function rebuildInstitutionOptions() {
    const select = document.getElementById("review-filter-source");
    if (!select) return;

    const requested = sessionStorage.getItem(FILTER_SOURCE_KEY) || select.value || "";
    select.replaceChildren(new Option("ALL INSTITUTIONS", ""));

    [...sourcesById.values()]
      .sort((left, right) => left.source_name.localeCompare(right.source_name))
      .forEach((source) => {
        select.add(new Option(source.source_name, source.source_id));
      });

    select.value = sourcesById.has(requested) ? requested : "";
    if (!select.value) sessionStorage.removeItem(FILTER_SOURCE_KEY);
  }

  async function loadInstitutions() {
    try {
      const response = await fetch(REVIEW_STATE_PATH, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || !Array.isArray(payload.sources)) return;

      sourcesById = new Map();
      sourceIdByName = new Map();

      payload.sources.forEach((raw) => {
        const sourceId = text(raw.source_id);
        const sourceNameValue = text(raw.source_name || raw.source_id);
        if (!sourceId || !sourceNameValue) return;
        const source = { source_id: sourceId, source_name: sourceNameValue };
        sourcesById.set(sourceId, source);
        sourceIdByName.set(sourceNameValue, sourceId);
      });

      rebuildInstitutionOptions();
      applyFilters();
      syncFeedbackSource(selectedSourceId());
      publishSourceChange();
    } catch {
      // Main page status already reports review-state failures.
    }
  }

  function applyFilters() {
    const sourceValue = selectedSourceId();
    const statusValue = document.getElementById("review-filter-status")?.value || "";

    allCards().forEach((card) => {
      const sourceId = cardSourceId(card);
      const status = cardStatus(card);
      const sourceMatches = !sourceValue || sourceId === sourceValue;
      const statusMatches = !statusValue
        || status === statusValue
        || (statusValue === "reviewed" && status !== "pending");
      card.hidden = !(sourceMatches && statusMatches);
    });
  }

  function captureScrollForAction(event) {
    const button = event.target.closest("#listing-pages button, #event-candidates button");
    if (!button) return;
    restoreScrollY = window.scrollY;
  }

  function scheduleRefresh() {
    applyFilters();
    syncFeedbackSource(selectedSourceId());
    if (restoreScrollY === null) return;

    window.clearTimeout(restoreTimer);
    restoreTimer = window.setTimeout(() => {
      window.scrollTo({ top: restoreScrollY, left: 0, behavior: "auto" });
      restoreScrollY = null;
    }, 0);
  }

  document.addEventListener("DOMContentLoaded", () => {
    ensureFilters();
    loadInstitutions();
    document.addEventListener("click", captureScrollForAction, true);

    const feedbackSource = document.getElementById("feedback-source");
    feedbackSource?.addEventListener("change", () => {
      if (syncingSource) return;
      const sourceId = text(feedbackSource.value);
      if (sourcesById.has(sourceId)) {
        setGlobalSource(sourceId, { syncFeedback: false });
      }
    });

    const observer = new MutationObserver(scheduleRefresh);
    const listing = document.getElementById("listing-pages");
    const events = document.getElementById("event-candidates");
    if (listing) observer.observe(listing, { childList: true });
    if (events) observer.observe(events, { childList: true });
    if (feedbackSource) observer.observe(feedbackSource, { childList: true });
  });

  window.InfoScreenReviewContext = {
    selectedSourceId,
    sourceName,
    applyFilters,
    setGlobalSource,
  };
})();
