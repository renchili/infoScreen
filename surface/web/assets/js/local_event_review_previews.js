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

  function publishState(payload) {
    document.dispatchEvent(new CustomEvent("infoscreen:review-state", {
      detail: payload,
    }));
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
      message.textContent = "No Event candidates were returned for this page. The diagnostic below must explain the exact failed recognition stage.";
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

  function setGlobalStatus(message, kind) {
    const status = document.getElementById("global-status");
    if (!status) return;
    status.textContent = message;
    status.className = `status ${kind || ""}`.trim();
  }

  async function collectConfirmedPages() {
    return request("/api/local-events/review/collect-events", {
      method: "POST",
      body: "{}",
    });
  }

  async function collectPreviewPage(url) {
    return request("/api/local-events/review/preview-events", {
      method: "POST",
      body: JSON.stringify({ listing_url: url }),
    });
  }

  async function collectPreview(card, button) {
    const url = listingUrl(card);
    if (!url) return;

    button.disabled = true;
    button.textContent = "PREVIEWING THIS PAGE...";
    setGlobalStatus("COLLECTING ISOLATED EVENT PREVIEW", "warn");

    try {
      const payload = await collectPreviewPage(url);
      const rows = normalizedPreviewRows(payload, url);
      savePreview(url, rows);
      publishState(payload);
      if (card.isConnected) {
        renderPreviewRows(card, rows, { collectedAt: new Date().toISOString() });
      }

      setGlobalStatus(
        `${rows.length} EVENT CANDIDATE${rows.length === 1 ? "" : "S"} PREVIEWED; REVIEW DECISION UNCHANGED`,
        rows.length ? "ok" : "error",
      );
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
      sourceId ? `COLLECTING ALL CONFIRMED PAGES; REPORTING ${sourceName}` : "COLLECTING ALL CONFIRMED PAGES",
      "warn",
    );

    try {
      const payload = await collectConfirmedPages();
      publishState(payload);
      const count = sourceId
        ? (payload.events || []).filter((row) => row.source_id === sourceId).length
        : (payload.events || []).length;
      setGlobalStatus(
        sourceId
          ? `${count} EVENT CANDIDATES RETURNED FOR ${sourceName}`
          : `${count} EVENT CANDIDATES RETURNED`,
        count ? "ok" : "error",
      );
      await window.InfoScreenReviewStudio?.loadState?.();
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

    document.addEventListener("infoscreen:review-rendered", () => {
      enhanceListingCards();
      window.InfoScreenReviewContext?.applyFilters?.();
    });
  });
})();
