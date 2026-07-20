"use strict";

(() => {
  const FILTER_SOURCE_KEY = "infoscreen.review.filter.source";
  const FILTER_STATUS_KEY = "infoscreen.review.filter.status";
  let restoreScrollY = null;
  let restoreTimer = null;

  function cardInstitution(card) {
    const heading = card.querySelector(".card-head h3 a, .card-head h3, .card-head h4");
    if (heading && heading.textContent.trim()) return heading.textContent.trim();
    for (const row of card.querySelectorAll(".meta > div")) {
      const value = row.textContent.trim();
      if (value.startsWith("Institution:")) {
        return value.slice("Institution:".length).trim();
      }
    }
    return "Unknown institution";
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

  function ensureFilters() {
    const toolbar = document.querySelector(".toolbar");
    if (!toolbar || document.getElementById("review-filter-source")) return;

    const group = document.createElement("div");
    group.className = "review-filters";
    group.innerHTML = `
      <label>
        <span>Institution</span>
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
    source.value = sessionStorage.getItem(FILTER_SOURCE_KEY) || "";
    status.value = sessionStorage.getItem(FILTER_STATUS_KEY) || "";
    source.addEventListener("change", () => {
      sessionStorage.setItem(FILTER_SOURCE_KEY, source.value);
      applyFilters();
    });
    status.addEventListener("change", () => {
      sessionStorage.setItem(FILTER_STATUS_KEY, status.value);
      applyFilters();
    });
  }

  function refreshInstitutionOptions() {
    const select = document.getElementById("review-filter-source");
    if (!select) return;
    const current = select.value;
    const names = [...new Set(allCards().map(cardInstitution))].sort((a, b) => a.localeCompare(b));
    select.replaceChildren(new Option("ALL INSTITUTIONS", ""));
    names.forEach((name) => select.add(new Option(name, name)));
    select.value = names.includes(current) ? current : "";
  }

  function applyFilters() {
    const sourceValue = document.getElementById("review-filter-source")?.value || "";
    const statusValue = document.getElementById("review-filter-status")?.value || "";
    allCards().forEach((card) => {
      const institution = cardInstitution(card);
      const status = cardStatus(card);
      const sourceMatches = !sourceValue || institution === sourceValue;
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

  function scheduleRestore() {
    refreshInstitutionOptions();
    applyFilters();
    if (restoreScrollY === null) return;
    window.clearTimeout(restoreTimer);
    restoreTimer = window.setTimeout(() => {
      window.scrollTo({ top: restoreScrollY, left: 0, behavior: "instant" });
      restoreScrollY = null;
    }, 0);
  }

  document.addEventListener("DOMContentLoaded", () => {
    ensureFilters();
    refreshInstitutionOptions();
    applyFilters();
    document.addEventListener("click", captureScrollForAction, true);

    const observer = new MutationObserver(scheduleRestore);
    const listing = document.getElementById("listing-pages");
    const events = document.getElementById("event-candidates");
    if (listing) observer.observe(listing, { childList: true });
    if (events) observer.observe(events, { childList: true });
  });
})();
