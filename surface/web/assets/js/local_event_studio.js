"use strict";

(() => {
  const ui = {};
  const state = {
    payload: null,
    feedbackSourceId: "",
    feedbackListingUrl: "",
    timer: null,
    busy: false,
  };

  const byId = (id) => document.getElementById(id);
  const text = (value, fallback = "—") => String(value ?? "").trim() || fallback;

  async function request(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const payload = await response
      .json()
      .catch(async () => ({ error: await response.text() }));
    if (!response.ok) {
      const detail = payload.detail ? `: ${payload.detail}` : "";
      throw new Error(`${payload.error || `HTTP ${response.status}`}${detail}`);
    }
    return payload;
  }

  function setStatus(node, message, kind = "") {
    node.textContent = message;
    node.className = `status ${kind}`.trim();
  }

  function clear(node) {
    while (node.firstChild) node.firstChild.remove();
  }

  function empty(node, message) {
    clear(node);
    const value = document.createElement("div");
    value.className = "empty";
    value.textContent = message;
    node.appendChild(value);
  }

  function badge(decision) {
    const node = document.createElement("span");
    node.className = `badge ${decision || "pending"}`;
    node.textContent = decision || "pending";
    return node;
  }

  function externalLink(url, label) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = label;
    return link;
  }

  function actionButton(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `button small ${className || ""}`.trim();
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function metaRow(label, value, code = false) {
    const row = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = `${label}: `;
    row.appendChild(strong);
    if (code) {
      const node = document.createElement("code");
      node.textContent = text(value);
      row.appendChild(node);
    } else {
      row.appendChild(document.createTextNode(text(value)));
    }
    return row;
  }

  async function setListingDecision(candidateId, decision) {
    setStatus(ui.globalStatus, "SAVING LIST PAGE REVIEW", "warn");
    await request("/api/local-events/review/listing-decision", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId, decision }),
    });
    await loadState();
  }

  async function setEventDecision(candidateId, decision) {
    setStatus(ui.globalStatus, "SAVING EVENT REVIEW", "warn");
    await request("/api/local-events/review/event-decision", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId, decision }),
    });
    await loadState();
  }

  function renderListingPages(rows) {
    clear(ui.listingPages);
    ui.listingCount.textContent = String(rows.length);
    if (!rows.length) {
      empty(ui.listingPages, "No list pages collected yet.");
      return;
    }

    rows.forEach((row) => {
      const article = document.createElement("article");
      article.className = `card ${row.decision || "pending"}`;

      const head = document.createElement("div");
      head.className = "card-head";
      const heading = document.createElement("h3");
      heading.appendChild(externalLink(row.url, row.source_name || row.source_id));
      head.append(heading, badge(row.decision));

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.append(
        metaRow("URL", row.url, true),
        metaRow("Found as", row.origin),
      );
      if (row.link_text) meta.appendChild(metaRow("Link text", row.link_text));

      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(
        actionButton("CONFIRM LIST PAGE", "primary", () =>
          setListingDecision(row.candidate_id, "confirmed"),
        ),
        actionButton("REJECT", "reject", () =>
          setListingDecision(row.candidate_id, "rejected"),
        ),
        actionButton("RESET", "secondary", () =>
          setListingDecision(row.candidate_id, "pending"),
        ),
      );

      article.append(head, meta, actions);
      ui.listingPages.appendChild(article);
    });
  }

  function positionText(position) {
    const value = position || {};
    return `x=${value.x ?? 0}, y=${value.y ?? 0}, w=${value.width ?? 0}, h=${value.height ?? 0}`;
  }

  function renderEventCandidates(rows) {
    clear(ui.eventCandidates);
    ui.eventCount.textContent = String(rows.length);
    if (!rows.length) {
      empty(ui.eventCandidates, "No Event candidates collected from confirmed pages yet.");
      return;
    }

    rows.forEach((row) => {
      const evidence = row.evidence || {};
      const article = document.createElement("article");
      article.className = `card ${row.decision || "pending"}`;

      const head = document.createElement("div");
      head.className = "card-head";
      const heading = document.createElement("h3");
      heading.appendChild(externalLink(row.detail_url, text(row.title, "Untitled candidate")));
      head.append(heading, badge(row.decision));

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.append(
        metaRow("Institution", row.source_name || row.source_id),
        metaRow("Listing page", row.listing_url, true),
        metaRow("Source element", evidence.selector, true),
        metaRow(
          "Element match",
          `${Number(evidence.selector_index ?? 0) + 1} of ${evidence.selector_match_count ?? 1}`,
        ),
        metaRow("Document position", positionText(evidence.document_position)),
        metaRow("Page index", evidence.page_index ?? 0),
      );

      if (evidence.text) {
        const snippet = document.createElement("div");
        snippet.className = "snippet";
        snippet.textContent = evidence.text;
        article.append(head, meta, snippet);
      } else {
        article.append(head, meta);
      }

      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(
        actionButton("RELATED ACTIVITY", "primary", () =>
          setEventDecision(row.candidate_id, "confirmed"),
        ),
        actionButton("NOT RELATED", "reject", () =>
          setEventDecision(row.candidate_id, "rejected"),
        ),
        actionButton("RESET", "secondary", () =>
          setEventDecision(row.candidate_id, "pending"),
        ),
      );
      article.appendChild(actions);
      ui.eventCandidates.appendChild(article);
    });
  }

  function renderFeedback(rows) {
    clear(ui.feedbackList);
    ui.feedbackCount.textContent = String(rows.length);
    if (!rows.length) {
      empty(ui.feedbackList, "No user-submitted Event positions yet.");
      return;
    }

    rows.forEach((row) => {
      const article = document.createElement("article");
      article.className = "card";
      const head = document.createElement("div");
      head.className = "card-head";
      const heading = document.createElement("h4");
      heading.textContent = row.source_name || row.source_id;
      head.append(heading, badge("confirmed"));

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.append(
        metaRow("Listing page", row.listing_url, true),
        metaRow("Page at submission", row.page_url, true),
        metaRow("Selected element", row.selector, true),
        metaRow(
          "Element match",
          `${Number(row.selector_index ?? 0) + 1} of ${row.selector_match_count ?? 1}`,
        ),
        metaRow("Document position", positionText(row.document_position)),
      );
      if (row.href) meta.appendChild(metaRow("Link", row.href, true));

      const snippet = document.createElement("div");
      snippet.className = "snippet";
      snippet.textContent = text(row.text, "No visible text");
      article.append(head, meta, snippet);
      ui.feedbackList.appendChild(article);
    });
  }

  function listingRowsForSource(sourceId) {
    const rows = state.payload?.listing_pages || [];
    return rows.filter((row) => row.source_id === sourceId);
  }

  function populateFeedbackSources() {
    const sources = state.payload?.sources || [];
    const available = sources.filter(
      (source) => listingRowsForSource(source.source_id).length > 0,
    );
    clear(ui.feedbackSource);
    available.forEach((source) => {
      const option = document.createElement("option");
      option.value = source.source_id;
      option.textContent = source.source_name || source.source_id;
      ui.feedbackSource.appendChild(option);
    });
    if (!available.length) {
      state.feedbackSourceId = "";
      state.feedbackListingUrl = "";
      ui.openFeedback.disabled = true;
      clear(ui.feedbackListing);
      return;
    }
    if (!available.some((source) => source.source_id === state.feedbackSourceId)) {
      state.feedbackSourceId = available[0].source_id;
    }
    ui.feedbackSource.value = state.feedbackSourceId;
    populateFeedbackListings();
  }

  function populateFeedbackListings() {
    const rows = listingRowsForSource(state.feedbackSourceId);
    clear(ui.feedbackListing);
    rows.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.url;
      option.textContent = `${row.url} [${row.decision}]`;
      ui.feedbackListing.appendChild(option);
    });
    if (!rows.length) {
      state.feedbackListingUrl = "";
      ui.openFeedback.disabled = true;
      return;
    }
    if (!rows.some((row) => row.url === state.feedbackListingUrl)) {
      state.feedbackListingUrl = rows[0].url;
    }
    ui.feedbackListing.value = state.feedbackListingUrl;
    ui.openFeedback.disabled = false;
  }

  function render(payload) {
    state.payload = payload;
    renderListingPages(payload.listing_pages || []);
    renderEventCandidates(payload.events || []);
    renderFeedback(payload.feedback || []);
    populateFeedbackSources();
    setStatus(ui.globalStatus, "READY", "ok");
  }

  async function loadState() {
    try {
      const payload = await request("/api/local-events/review/state");
      render(payload);
    } catch (error) {
      setStatus(ui.globalStatus, error.message, "error");
    }
  }

  async function runCollection(button, statusText, path) {
    if (state.busy) return;
    state.busy = true;
    button.disabled = true;
    setStatus(ui.globalStatus, statusText, "warn");
    try {
      const payload = await request(path, { method: "POST", body: "{}" });
      render(payload);
    } catch (error) {
      setStatus(ui.globalStatus, error.message, "error");
    } finally {
      state.busy = false;
      button.disabled = false;
    }
  }

  async function openFeedbackBrowser() {
    if (!state.feedbackSourceId || !state.feedbackListingUrl) return;
    ui.openFeedback.disabled = true;
    setStatus(ui.feedbackStatus, "OPENING CHROMIUM", "warn");
    ui.feedbackMessage.textContent = "Opening the real listing page on the Surface desktop...";
    try {
      await request("/api/local-events/review/open-feedback", {
        method: "POST",
        body: JSON.stringify({
          source_id: state.feedbackSourceId,
          listing_url: state.feedbackListingUrl,
        }),
      });
      setStatus(ui.feedbackStatus, "BROWSER OPEN", "ok");
      ui.feedbackMessage.textContent =
        "Browse normally. When needed, click POINT TO EVENT in the browser toolbar, choose the element, then submit.";
    } catch (error) {
      setStatus(ui.feedbackStatus, "FAILED", "error");
      ui.feedbackMessage.textContent = error.message;
    } finally {
      ui.openFeedback.disabled = false;
    }
  }

  function initialize() {
    Object.assign(ui, {
      globalStatus: byId("global-status"),
      collectListings: byId("collect-listings"),
      collectEvents: byId("collect-events"),
      reload: byId("reload-state"),
      listingPages: byId("listing-pages"),
      listingCount: byId("listing-count"),
      eventCandidates: byId("event-candidates"),
      eventCount: byId("event-count"),
      feedbackStatus: byId("feedback-status"),
      feedbackSource: byId("feedback-source"),
      feedbackListing: byId("feedback-listing"),
      openFeedback: byId("open-feedback-browser"),
      feedbackMessage: byId("feedback-message"),
      feedbackList: byId("feedback-list"),
      feedbackCount: byId("feedback-count"),
    });

    ui.collectListings.addEventListener("click", () =>
      runCollection(
        ui.collectListings,
        "COLLECTING LIST PAGES",
        "/api/local-events/review/discover-listings",
      ),
    );
    ui.collectEvents.addEventListener("click", () =>
      runCollection(
        ui.collectEvents,
        "COLLECTING EVENTS FROM CONFIRMED PAGES",
        "/api/local-events/review/collect-events",
      ),
    );
    ui.reload.addEventListener("click", loadState);
    ui.feedbackSource.addEventListener("change", () => {
      state.feedbackSourceId = ui.feedbackSource.value;
      state.feedbackListingUrl = "";
      populateFeedbackListings();
    });
    ui.feedbackListing.addEventListener("change", () => {
      state.feedbackListingUrl = ui.feedbackListing.value;
    });
    ui.openFeedback.addEventListener("click", openFeedbackBrowser);

    loadState();
    state.timer = window.setInterval(loadState, 3000);
  }

  document.addEventListener("DOMContentLoaded", initialize);
})();
