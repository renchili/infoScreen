"use strict";

(() => {
  const PREVIEW_STORAGE_KEY = "infoscreen.review.event-previews";
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

  function previews() {
    try {
      const value = JSON.parse(sessionStorage.getItem(PREVIEW_STORAGE_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch {
      return {};
    }
  }

  function savePreview(url, rows) {
    const value = previews();
    value[url] = {
      collected_at: new Date().toISOString(),
      events: rows,
    };
    sessionStorage.setItem(PREVIEW_STORAGE_KEY, JSON.stringify(value));
  }

  function listingUrl(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      if (!row.textContent.trim().startsWith("URL:")) continue;
      return text(row.querySelector("code")?.textContent || row.textContent.replace(/^URL:\s*/, ""));
    }
    return "";
  }

  function listingSourceId(card) {
    return text(card.dataset.sourceId);
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

  function rowsFromRenderedCards(url) {
    return eventRowsFor(url).map((card) => {
      const title = text(card.querySelector(".card-head h3")?.textContent);
      const meta = [...card.querySelectorAll(".meta > div")].map((row) => text(row.textContent));
      const value = (prefix) => text(meta.find((row) => row.startsWith(prefix))?.slice(prefix.length));
      return {
        title,
        when: value("When:"),
        where: value("Where:"),
        detail_status: value("Detail status:"),
        detail_url: card.querySelector(".card-head h3 a")?.href || "",
      };
    });
  }

  function normalizedPreviewRows(payload, url) {
    return (payload.events || [])
      .filter((row) => text(row.listing_url) === url)
      .map((row) => ({
        title: text(row.title) || "Untitled candidate",
        when: text(row.when),
        where: text(row.where),
        detail_status: text(row.detail_status),
        detail_url: text(row.detail_url),
      }));
  }

  function ensurePreviewBox(card) {
    let box = card.querySelector(".listing-event-preview");
    if (box) return box;
    box = document.createElement("div");
    box.className = "listing-event-preview";
    card.querySelector(".actions")?.before(box);
    return box;
  }

  function renderPreviewRows(card, rows, { error = "", collectedAt = "" } = {}) {
    const box = ensurePreviewBox(card);
    box.replaceChildren();

    const heading = document.createElement("div");
    heading.className = "listing-event-preview-heading";
    heading.textContent = error
      ? "EVENT PREVIEW FAILED"
      : `EVENT PREVIEW · ${rows.length}`;
    box.appendChild(heading);

    if (error) {
      const message = document.createElement("div");
      message.className = "preview-warning";
      message.textContent = error;
      box.appendChild(message);
      return;
    }

    if (!rows.length) {
      const message = document.createElement("div");
      message.className = "preview-warning";
      message.textContent = "No Event candidates were returned for this page. Do not confirm it as a list page without checking the real page.";
      box.appendChild(message);
      return;
    }

    if (rows.length < 2) {
      const warning = document.createElement("div");
      warning.className = "preview-warning";
      warning.textContent = "Only one Event candidate was found. This may be a detail page rather than a repeated Event list.";
      box.appendChild(warning);
    }

    if (collectedAt) {
      const time = document.createElement("div");
      time.className = "listing-event-preview-time";
      time.textContent = `Collected ${new Date(collectedAt).toLocaleString()}`;
      box.appendChild(time);
    }

    const list = document.createElement("ol");
    list.className = "listing-event-preview-list";
    rows.slice(0, 10).forEach((row) => {
      const item = document.createElement("li");
      const title = row.detail_url ? document.createElement("a") : document.createElement("strong");
      if (row.detail_url) {
        title.href = row.detail_url;
        title.target = "_blank";
        title.rel = "noopener";
      }
      title.textContent = row.title || "Untitled candidate";
      item.appendChild(title);

      const facts = [row.when, row.where, row.detail_status].filter(Boolean);
      if (facts.length) {
        const meta = document.createElement("div");
        meta.className = "listing-event-preview-meta";
        meta.textContent = facts.join(" · ");
        item.appendChild(meta);
      }
      list.appendChild(item);
    });
    box.appendChild(list);
  }

  function previewSummary(card, url) {
    const stored = previews()[url];
    if (stored && Array.isArray(stored.events)) {
      renderPreviewRows(card, stored.events, { collectedAt: stored.collected_at });
      return;
    }

    const rendered = rowsFromRenderedCards(url);
    if (rendered.length) {
      renderPreviewRows(card, rendered);
      return;
    }

    const box = ensurePreviewBox(card);
    box.innerHTML = '<div class="listing-event-preview-heading">EVENT PREVIEW · NOT COLLECTED</div>';
  }

  async function setListingDecision(candidateId, decision) {
    return request("/api/local-events/review/listing-decision", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId, decision }),
    });
  }

  async function withExclusiveConfirmedListings(state, targetIds, action) {
    const changed = [];
    document.documentElement.classList.add("review-sequence-busy");

    try {
      for (const row of state.listing_pages || []) {
        let desired = row.decision || "pending";
        if (targetIds.has(row.candidate_id)) {
          desired = "confirmed";
        } else if (desired === "confirmed") {
          desired = "pending";
        }

        if (desired === row.decision) continue;
        changed.push({ candidate_id: row.candidate_id, decision: row.decision || "pending" });
        await setListingDecision(row.candidate_id, desired);
      }
      return await action();
    } finally {
      for (const row of changed.reverse()) {
        try {
          await setListingDecision(row.candidate_id, row.decision);
        } catch {
          // The visible status below reports collection errors; restoration is retried by reload.
        }
      }
      document.documentElement.classList.remove("review-sequence-busy");
    }
  }

  function setGlobalStatus(message, kind) {
    const status = document.getElementById("global-status");
    if (!status) return;
    status.textContent = message;
    status.className = `status ${kind || ""}`.trim();
  }

  async function reloadState() {
    document.getElementById("reload-state")?.click();
  }

  async function collectPreview(card, button) {
    const url = listingUrl(card);
    if (!url) return;

    button.disabled = true;
    button.textContent = "COLLECTING THIS PAGE...";
    setGlobalStatus("COLLECTING EVENT PREVIEW FOR ONE LIST PAGE", "warn");

    try {
      const state = await request("/api/local-events/review/state");
      const listing = (state.listing_pages || []).find((row) => row.url === url);
      if (!listing) throw new Error("Listing page is not present in review state");

      const payload = await withExclusiveConfirmedListings(
        state,
        new Set([listing.candidate_id]),
        () => request("/api/local-events/review/collect-events", {
          method: "POST",
          body: "{}",
        }),
      );

      const rows = normalizedPreviewRows(payload, url);
      savePreview(url, rows);
      if (card.isConnected) {
        renderPreviewRows(card, rows, { collectedAt: new Date().toISOString() });
      }

      setGlobalStatus(
        `${rows.length} EVENT CANDIDATE${rows.length === 1 ? "" : "S"} RETURNED FOR THIS LIST PAGE`,
        rows.length ? "ok" : "error",
      );
      await reloadState();
    } catch (error) {
      if (card.isConnected) {
        renderPreviewRows(card, [], { error: text(error.message || error) });
      }
      setGlobalStatus(text(error.message || error), "error");
    } finally {
      button.disabled = false;
      button.textContent = "PREVIEW EVENTS";
    }
  }

  async function collectForGlobalInstitution(button) {
    const sourceId = window.InfoScreenReviewContext?.selectedSourceId?.() || "";
    const sourceName = window.InfoScreenReviewContext?.sourceName?.(sourceId) || sourceId;

    button.disabled = true;
    setGlobalStatus(
      sourceId ? `COLLECTING CONFIRMED PAGES FOR ${sourceName}` : "COLLECTING ALL CONFIRMED PAGES",
      "warn",
    );

    try {
      if (!sourceId) {
        const payload = await request("/api/local-events/review/collect-events", {
          method: "POST",
          body: "{}",
        });
        setGlobalStatus(`${(payload.events || []).length} EVENT CANDIDATES RETURNED`, "ok");
        await reloadState();
        return;
      }

      const state = await request("/api/local-events/review/state");
      const selected = (state.listing_pages || []).filter(
        (row) => row.source_id === sourceId && row.decision === "confirmed",
      );
      if (!selected.length) {
        throw new Error(`No confirmed list pages for ${sourceName}`);
      }

      const payload = await withExclusiveConfirmedListings(
        state,
        new Set(selected.map((row) => row.candidate_id)),
        () => request("/api/local-events/review/collect-events", {
          method: "POST",
          body: "{}",
        }),
      );

      const count = (payload.events || []).filter((row) => row.source_id === sourceId).length;
      setGlobalStatus(`${count} EVENT CANDIDATES RETURNED FOR ${sourceName}`, count ? "ok" : "error");
      await reloadState();
    } catch (error) {
      setGlobalStatus(text(error.message || error), "error");
    } finally {
      button.disabled = false;
    }
  }

  function replaceGlobalCollectButton() {
    const original = document.getElementById("collect-events");
    if (!original || original.dataset.scoped === "true") return;

    const button = original.cloneNode(true);
    button.dataset.scoped = "true";
    button.addEventListener("click", () => collectForGlobalInstitution(button));
    original.replaceWith(button);
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
    replaceGlobalCollectButton();
    enhanceListingCards();

    const listing = document.getElementById("listing-pages");
    const events = document.getElementById("event-candidates");
    const observer = new MutationObserver(() => {
      enhanceListingCards();
      window.InfoScreenReviewContext?.applyFilters?.();
    });
    if (listing) observer.observe(listing, { childList: true });
    if (events) observer.observe(events, { childList: true });
  });
})();
