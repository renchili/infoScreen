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

  function diagnosticFor(payload, url) {
    const rows = payload?.event_collection?.listing_diagnostics;
    if (!Array.isArray(rows)) return null;
    return rows.find((row) => text(row?.listing_url) === url) || null;
  }

  function stage(label, value) {
    const row = document.createElement("div");
    const name = document.createElement("span");
    const count = document.createElement("strong");
    name.textContent = label;
    count.textContent = String(value ?? 0);
    row.append(name, count);
    return row;
  }

  function renderDiagnostic(card, diagnostic) {
    const preview = card.querySelector(".listing-event-preview");
    if (!preview) return;

    preview.querySelector(".listing-event-diagnostic")?.remove();

    const block = document.createElement("section");
    block.className = "listing-event-diagnostic";

    const title = document.createElement("div");
    title.className = "listing-event-diagnostic-title";
    title.textContent = "WHY NO EVENT WAS RECOGNISED";
    block.appendChild(title);

    if (!diagnostic) {
      const message = document.createElement("div");
      message.className = "preview-warning";
      message.textContent = "No diagnostic record exists for this collection. Run PREVIEW EVENTS again after updating the service.";
      block.appendChild(message);
      preview.appendChild(block);
      return;
    }

    const code = document.createElement("code");
    code.className = "listing-event-diagnostic-code";
    code.textContent = text(diagnostic.reason_code) || "unknown_reason";
    block.appendChild(code);

    const reason = document.createElement("div");
    reason.className = "listing-event-diagnostic-reason";
    reason.textContent = text(diagnostic.reason) || "The collector did not provide a reason.";
    block.appendChild(reason);

    const stages = document.createElement("div");
    stages.className = "listing-event-diagnostic-stages";
    stages.append(
      stage("HTTP", diagnostic.http_status ?? "—"),
      stage("Visible links", diagnostic.visible_link_count),
      stage("Official-domain links", diagnostic.same_domain_link_count),
      stage("Possible detail links", diagnostic.detail_link_count),
      stage("Extracted DOM cards", diagnostic.extracted_card_count),
      stage("Admitted Event cards", diagnostic.admitted_card_count),
      stage("Cards with DOM evidence", diagnostic.cards_with_evidence),
      stage("Cards with selector", diagnostic.cards_with_selector),
      stage("Event candidates", diagnostic.candidates_created),
      stage("Detail collected", diagnostic.detail_collected),
      stage("Detail incomplete", diagnostic.detail_incomplete),
      stage("Detail failed", diagnostic.detail_failed),
    );
    block.appendChild(stages);

    const examples = Array.isArray(diagnostic.detail_link_examples)
      ? diagnostic.detail_link_examples.filter((item) => text(item?.url)).slice(0, 5)
      : [];
    if (examples.length) {
      const heading = document.createElement("div");
      heading.className = "listing-event-diagnostic-subtitle";
      heading.textContent = "DETAIL LINKS SEEN ON PAGE";
      block.appendChild(heading);

      const list = document.createElement("ol");
      list.className = "listing-event-diagnostic-links";
      examples.forEach((item) => {
        const row = document.createElement("li");
        const link = document.createElement("a");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = text(item.text) || item.url;
        row.appendChild(link);
        list.appendChild(row);
      });
      block.appendChild(list);
    }

    preview.appendChild(block);
  }

  function applyDiagnostics(payload) {
    lastPayload = payload;
    for (const card of document.querySelectorAll("#listing-pages > .card")) {
      const heading = card.querySelector(".listing-event-preview-heading");
      if (!heading || text(heading.textContent) !== "EVENT PREVIEW · 0") continue;
      const url = listingUrl(card);
      if (!url) continue;
      renderDiagnostic(card, diagnosticFor(payload, url));
    }
  }

  async function loadDiagnostics() {
    try {
      const response = await fetch(STATE_PATH, { cache: "no-store" });
      const payload = await response.json();
      if (response.ok) applyDiagnostics(payload);
    } catch {
      // The main page already exposes review-state request failures.
    }
  }

  function scheduleDiagnostics() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(loadDiagnostics, 80);
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadDiagnostics();
    const listing = document.getElementById("listing-pages");
    if (listing) {
      new MutationObserver(scheduleDiagnostics).observe(listing, {
        childList: true,
      });
    }
  });
})();
