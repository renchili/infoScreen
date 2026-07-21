"use strict";

(() => {
  const STATE_PATH = "/api/local-events/review/state";
  let refreshTimer = 0;
  let lastPayload = null;

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
      return text(row.querySelector("code")?.textContent || row.textContent.replace(/^URL:\s*/, ""));
    }
    return "";
  }

  function diagnostics(payload) {
    const rows = payload?.event_collection?.listing_diagnostics;
    return Array.isArray(rows) ? rows : [];
  }

  function diagnosticFor(payload, url) {
    const expected = canonical(url);
    return diagnostics(payload).find((row) => canonical(row?.listing_url) === expected) || null;
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

  function missingDiagnosticReason(payload, url) {
    const collection = payload?.event_collection || {};
    const rows = diagnostics(payload);
    if (!text(collection.completed_at)) {
      return {
        code: "collection_not_run_for_this_state",
        reason: "No completed Event collection is present in the current backend state.",
      };
    }
    if (!rows.length) {
      return {
        code: "backend_diagnostics_not_loaded",
        reason: "The browser assets are newer than the running Python backend. Restart infoscreen-http.service, then run PREVIEW EVENTS again. The old backend cannot explain why this page returned zero Events.",
      };
    }
    return {
      code: "diagnostic_scope_did_not_include_page",
      reason: `The last collection contains diagnostics, but not for ${url}. Run PREVIEW EVENTS on this exact list page again.`,
    };
  }

  function renderDiagnostic(card, diagnostic, payload, url) {
    const preview = card.querySelector(".listing-event-preview");
    if (!preview) return;

    preview.querySelector(".listing-event-diagnostic")?.remove();

    const block = document.createElement("section");
    block.className = "listing-event-diagnostic";

    const title = document.createElement("div");
    title.className = "listing-event-diagnostic-title";
    title.textContent = "WHY NO EVENT WAS RECOGNISED";
    block.appendChild(title);

    const fallback = diagnostic ? null : missingDiagnosticReason(payload, url);
    const code = document.createElement("code");
    code.className = "listing-event-diagnostic-code";
    code.textContent = text(diagnostic?.reason_code) || fallback.code;
    block.appendChild(code);

    const reason = document.createElement("div");
    reason.className = "listing-event-diagnostic-reason";
    reason.textContent = text(diagnostic?.reason) || fallback.reason;
    block.appendChild(reason);

    if (!diagnostic) {
      preview.appendChild(block);
      return;
    }

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
      renderDiagnostic(card, diagnosticFor(payload, url), payload, url);
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
    refreshTimer = window.setTimeout(() => {
      if (lastPayload) applyDiagnostics(lastPayload);
    }, 40);
  }

  document.addEventListener("infoscreen:review-state", (event) => {
    if (event.detail && typeof event.detail === "object") applyDiagnostics(event.detail);
  });

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
