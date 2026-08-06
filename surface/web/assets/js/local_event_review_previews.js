"use strict";

(() => {
  const ACTIVE_PREVIEW_KEY = "infoscreen.review.active-preview-panel";
  const PREVIEW_STORAGE_KEY = "infoscreen.review.event-previews";
  const PREVIEW_AUTHORITY_VERSION = "detail-provenance-v2";
  const PREVIEW_PANEL_VERSION = 1;
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

  function canonical(value) {
    const raw = text(value);
    if (!raw) return "";
    try {
      const url = new URL(raw, window.location.href);
      url.hash = "";
      if (url.pathname !== "/") url.pathname = url.pathname.replace(/\/$/, "");
      return url.href;
    } catch {
      return raw;
    }
  }

  function previews() {
    try {
      const value = JSON.parse(sessionStorage.getItem(PREVIEW_STORAGE_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch {
      return {};
    }
  }

  function diagnosticFor(payload, url) {
    const expected = canonical(url);
    const rows = payload?.event_collection?.listing_diagnostics;
    if (!Array.isArray(rows)) return null;
    return rows.find((row) => canonical(row?.listing_url) === expected) || null;
  }

  function normalizedPosition(value) {
    const position = value && typeof value === "object" ? value : {};
    return {
      x: Number(position.x ?? 0),
      y: Number(position.y ?? 0),
      width: Number(position.width ?? 0),
      height: Number(position.height ?? 0),
    };
  }

  function normalizedPreviewCandidates(payload, url) {
    const expected = canonical(url);
    return (payload.events || [])
      .filter((row) => canonical(row.listing_url) === expected)
      .map((row) => {
        const evidence = row.evidence && typeof row.evidence === "object"
          ? row.evidence
          : {};
        return {
          candidate_id: text(row.candidate_id),
          source_id: text(row.source_id),
          source_name: text(row.source_name),
          listing_url: expected,
          detail_url: canonical(row.detail_url),
          title: text(row.title) || "Untitled candidate",
          when: text(row.when),
          where: text(row.where),
          summary: text(row.summary),
          detail_status: text(row.detail_status),
          detail_error: text(row.detail_error),
          detail_page_title: text(row.detail_page_title),
          evidence: {
            selector: text(evidence.selector),
            selector_index: Number(evidence.selector_index ?? 0),
            selector_match_count: Number(evidence.selector_match_count ?? 1),
            document_position: normalizedPosition(evidence.document_position),
            viewport_position: normalizedPosition(evidence.viewport_position),
            page_index: Number(evidence.page_index ?? 0),
            page_url: canonical(evidence.page_url || expected),
            text: text(evidence.text),
          },
        };
      });
  }

  function normalizedListingDetailUrls(payload, candidates) {
    const raw = payload?.event_collection?.preview_candidate_listing_detail_urls;
    const values = raw && typeof raw === "object" ? raw : {};
    const accepted = new Set(candidates.map((row) => row.candidate_id));
    return Object.fromEntries(
      Object.entries(values)
        .filter(([candidateId, value]) =>
          accepted.has(text(candidateId)) && Boolean(canonical(value)),
        )
        .map(([candidateId, value]) => [text(candidateId), canonical(value)]),
    );
  }

  function previewSummaryRows(candidates) {
    return candidates.map((row) => ({
      title: row.title,
      when: row.when,
      where: row.where,
      detail_status: row.detail_status,
      detail_url: row.detail_url,
    }));
  }

  function savePreview(url, payload, diagnostic, authorityVersion) {
    const key = canonical(url);
    const candidates = normalizedPreviewCandidates(payload, key);
    const stored = {
      authority_version: text(authorityVersion),
      panel_version: PREVIEW_PANEL_VERSION,
      collected_at: new Date().toISOString(),
      events: previewSummaryRows(candidates),
      candidate_rows: candidates,
      listing_detail_urls: normalizedListingDetailUrls(payload, candidates),
      diagnostic: diagnostic && typeof diagnostic === "object" ? diagnostic : null,
    };
    const value = previews();
    Object.values(value).forEach((entry) => {
      if (!entry || typeof entry !== "object") return;
      delete entry.candidate_rows;
      delete entry.listing_detail_urls;
    });
    value[key] = stored;
    try {
      sessionStorage.setItem(PREVIEW_STORAGE_KEY, JSON.stringify(value));
    } catch {
      // The current Preview remains usable when session storage is unavailable.
    }
    return stored;
  }

  function storedPreview(url, { requireCandidates = false } = {}) {
    const expected = canonical(url);
    for (const [key, value] of Object.entries(previews())) {
      if (
        canonical(key) === expected
        && value
        && typeof value === "object"
        && value.authority_version === PREVIEW_AUTHORITY_VERSION
        && Array.isArray(value.events)
        && (
          !requireCandidates
          || (
            value.panel_version === PREVIEW_PANEL_VERSION
            && Array.isArray(value.candidate_rows)
          )
        )
      ) {
        return value;
      }
    }
    return null;
  }

  function activePreviewUrl() {
    try {
      const value = JSON.parse(sessionStorage.getItem(ACTIVE_PREVIEW_KEY) || "null");
      return canonical(value?.url || "");
    } catch {
      return "";
    }
  }

  function panelPayload(stored) {
    return {
      events: stored.candidate_rows,
      event_collection: {
        preview_candidate_listing_detail_urls: stored.listing_detail_urls || {},
      },
    };
  }

  function publishPreview(url, diagnostic, { restored = false } = {}) {
    document.dispatchEvent(new CustomEvent("infoscreen:review-preview", {
      detail: { url, diagnostic, restored },
    }));
  }

  function listingUrl(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      if (!row.textContent.trim().startsWith("URL:")) continue;
      return text(row.querySelector("code")?.textContent || row.textContent.replace(/^URL:\s*/, ""));
    }
    return "";
  }

  function listingDecision(card) {
    if (card.classList.contains("confirmed")) return "confirmed";
    if (card.classList.contains("rejected")) return "rejected";
    return "pending";
  }

  function previewButtonText(card) {
    return listingDecision(card) === "pending"
      ? "PREVIEW BEFORE CONFIRM"
      : "PREVIEW EVENTS";
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
    const stored = storedPreview(url);
    if (stored) {
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

  function candidateMetaRow(label, value, useCode = false) {
    const row = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = `${label}: `;
    row.appendChild(strong);
    const rendered = text(value) || "—";
    if (useCode) {
      const code = document.createElement("code");
      code.textContent = rendered;
      row.appendChild(code);
    } else {
      row.appendChild(document.createTextNode(rendered));
    }
    return row;
  }

  function positionText(position) {
    const value = position || {};
    return `x=${value.x ?? 0}, y=${value.y ?? 0}, w=${value.width ?? 0}, h=${value.height ?? 0}`;
  }

  function restoreCollectedPanelLabels() {
    const title = document.getElementById("event-candidates-title");
    const hint = document.getElementById("event-candidates-hint");
    if (title) title.textContent = "Collected event candidates";
    if (hint) {
      hint.textContent = "Every candidate shows its source element, match index, document position, and detail-page result.";
    }
  }

  function renderPreviewCandidatePanel(payload, url) {
    const container = document.getElementById("event-candidates");
    const count = document.getElementById("event-count");
    const title = document.getElementById("event-candidates-title");
    const hint = document.getElementById("event-candidates-hint");
    if (!container || !count) return;

    const expected = canonical(url);
    const rows = (payload.events || []).filter(
      (row) => canonical(row.listing_url) === expected,
    );
    const rawListingDetailUrls = payload?.event_collection?.preview_candidate_listing_detail_urls;
    const listingDetailUrls = rawListingDetailUrls && typeof rawListingDetailUrls === "object"
      ? rawListingDetailUrls
      : {};

    if (title) title.textContent = "Preview event candidates";
    if (hint) {
      hint.textContent = "Temporary candidates from the selected list page. Review every candidate as REAL EVENT or NOT EVENT; choices are committed only when the List Page review is saved.";
    }
    count.textContent = String(rows.length);
    container.replaceChildren();

    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No Event candidates were returned by this isolated preview.";
      container.appendChild(empty);
      return;
    }

    rows.forEach((row) => {
      const evidence = row.evidence || {};
      const article = document.createElement("article");
      article.className = "card pending";
      article.dataset.candidateId = row.candidate_id || "";
      article.dataset.sourceId = row.source_id || "";
      article.dataset.preview = "true";
      const listingDetailUrl = text(listingDetailUrls[row.candidate_id]);
      article.dataset.listingDetailUrl = listingDetailUrl
        ? canonical(listingDetailUrl)
        : (row.detail_url ? canonical(row.detail_url) : "");

      const head = document.createElement("div");
      head.className = "card-head";
      const heading = document.createElement("h3");
      if (row.detail_url) {
        const link = document.createElement("a");
        link.href = row.detail_url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = text(row.title) || "Untitled candidate";
        heading.appendChild(link);
      } else {
        heading.textContent = text(row.title) || "Untitled candidate";
      }
      const previewBadge = document.createElement("span");
      previewBadge.className = "badge pending";
      previewBadge.textContent = "preview";
      head.append(heading, previewBadge);

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.append(
        candidateMetaRow("Institution", row.source_name || row.source_id),
        candidateMetaRow("Detail status", row.detail_status),
        candidateMetaRow("When", row.when),
        candidateMetaRow("Where", row.where),
        candidateMetaRow("Detail page title", row.detail_page_title),
        candidateMetaRow("Listing page", row.listing_url, true),
        candidateMetaRow("Source element", evidence.selector, true),
        candidateMetaRow(
          "Element match",
          `${Number(evidence.selector_index ?? 0) + 1} of ${evidence.selector_match_count ?? 1}`,
        ),
        candidateMetaRow("Document position", positionText(evidence.document_position)),
        candidateMetaRow("Listing page index", evidence.page_index ?? 0),
      );
      if (row.detail_error) {
        meta.appendChild(candidateMetaRow("Detail issue", row.detail_error));
      }

      article.append(head, meta);
      const visibleText = row.summary || evidence.text;
      if (visibleText) {
        const snippet = document.createElement("div");
        snippet.className = "snippet";
        snippet.textContent = visibleText;
        article.appendChild(snippet);
      }

      const notice = document.createElement("div");
      notice.className = "snippet";
      notice.textContent = "TEMPORARY PREVIEW · Choose REAL EVENT or NOT EVENT; selections are not committed until the List Page review is saved.";
      article.appendChild(notice);
      container.appendChild(article);
    });

    window.InfoScreenReviewContext?.applyFilters?.();
  }

  function setGlobalStatus(message, kind) {
    const status = document.getElementById("global-status");
    if (!status) return;
    status.textContent = message;
    status.className = `status ${kind || ""}`.trim();
  }

  async function reloadState() {
    await window.InfoScreenReviewStudio?.loadState?.();
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
    button.textContent = "COLLECTING PREVIEW...";
    setGlobalStatus("COLLECTING EVENT PREVIEW", "warn");

    try {
      const payload = await collectPreviewPage(url);
      const diagnostic = diagnosticFor(payload, url);
      const stored = savePreview(
        url,
        payload,
        diagnostic,
        payload?.event_collection?.detail_field_authority_version,
      );
      const rows = stored.events;
      if (card.isConnected) {
        renderPreviewRows(card, rows, { collectedAt: stored.collected_at });
      }
      renderPreviewCandidatePanel(panelPayload(stored), url);
      publishPreview(url, diagnostic);

      setGlobalStatus(
        `${rows.length} EVENT CANDIDATE${rows.length === 1 ? "" : "S"} RETURNED FOR THIS LIST PAGE`,
        rows.length ? "ok" : "error",
      );
    } catch (error) {
      if (card.isConnected) {
        renderPreviewRows(card, [], { error: text(error.message || error) });
      }
      setGlobalStatus(text(error.message || error), "error");
    } finally {
      button.disabled = false;
      button.textContent = previewButtonText(card);
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

  function restoreActivePreview() {
    const url = activePreviewUrl();
    if (!url) return false;

    const card = [...document.querySelectorAll("#listing-pages > .card")]
      .find((candidate) => canonical(listingUrl(candidate)) === url);
    const stored = storedPreview(url, { requireCandidates: true });
    if (!stored) {
      try {
        sessionStorage.removeItem(ACTIVE_PREVIEW_KEY);
      } catch {
        // A stale active marker cannot block the normal server-owned panel.
      }
      return false;
    }
    if (!card) return false;

    renderPreviewRows(card, stored.events, { collectedAt: stored.collected_at });
    renderPreviewCandidatePanel(panelPayload(stored), url);
    publishPreview(url, stored.diagnostic, { restored: true });
    return true;
  }

  function enhanceListingCards() {
    for (const card of document.querySelectorAll("#listing-pages > .card")) {
      const url = listingUrl(card);
      if (!url) continue;
      previewSummary(card, url);

      const actions = card.querySelector(".actions");
      if (!actions) continue;

      let button = actions.querySelector(".preview-events-button");
      if (!button) {
        button = document.createElement("button");
        button.type = "button";
        button.className = "button small warning preview-events-button";
        button.addEventListener("click", () => collectPreview(card, button));
        actions.prepend(button);
      }

      button.dataset.decisionIndependent = "true";
      button.title = "Preview this saved list page without changing its review decision.";
      button.setAttribute("aria-label", button.title);
      if (!button.disabled) button.textContent = previewButtonText(card);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    replaceGlobalCollectButton();
    enhanceListingCards();

    document.addEventListener("infoscreen:review-rendered", () => {
      restoreCollectedPanelLabels();
      enhanceListingCards();
      restoreActivePreview();
      window.InfoScreenReviewContext?.applyFilters?.();
    });
  });
})();