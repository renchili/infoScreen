"use strict";

(() => {
  const ACTIVE_PREVIEW_KEY = "infoscreen.review.active-preview-panel";
  const DECISION_KEY = "infoscreen.review.preview-event-decisions";
  const PROTOCOL_PREFIX = "preview-review-v1:";
  const text = (value) => String(value || "").trim();

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

  function activePreviewUrl() {
    try {
      const value = JSON.parse(sessionStorage.getItem(ACTIVE_PREVIEW_KEY) || "null");
      return canonical(value?.url || "");
    } catch {
      return "";
    }
  }

  function allDecisions() {
    try {
      const value = JSON.parse(sessionStorage.getItem(DECISION_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch {
      return {};
    }
  }

  function decisionsFor(url) {
    const value = allDecisions()[canonical(url)];
    return value && typeof value === "object" ? value : {};
  }

  function saveDecisions(url, decisions) {
    const value = allDecisions();
    value[canonical(url)] = decisions;
    sessionStorage.setItem(DECISION_KEY, JSON.stringify(value));
  }

  function clearDecisions(url) {
    const value = allDecisions();
    delete value[canonical(url)];
    sessionStorage.setItem(DECISION_KEY, JSON.stringify(value));
  }

  function listingUrl(card) {
    for (const row of card.querySelectorAll(".meta > div")) {
      if (!text(row.textContent).startsWith("URL:")) continue;
      return canonical(
        row.querySelector("code")?.textContent
        || row.textContent.replace(/^URL:\s*/, ""),
      );
    }
    return "";
  }

  function listingCard(url) {
    const expected = canonical(url);
    return [...document.querySelectorAll("#listing-pages > .card")]
      .find((card) => listingUrl(card) === expected) || null;
  }

  function listingDecision(card) {
    if (card?.classList.contains("confirmed")) return "confirmed";
    if (card?.classList.contains("rejected")) return "rejected";
    return "pending";
  }

  function setGlobalStatus(message, kind = "") {
    const node = document.getElementById("global-status");
    if (!node) return;
    node.textContent = message;
    node.className = `status ${kind}`.trim();
  }

  async function request(path, body) {
    const response = await fetch(path, {
      method: "POST",
      cache: "no-store",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body || {}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  function previewCards() {
    return [...document.querySelectorAll('#event-candidates > [data-preview="true"]')];
  }

  function detailUrl(card) {
    return canonical(card.querySelector(".card-head h3 a")?.href || "");
  }

  function listingDetailUrl(card) {
    const value = text(card.dataset.listingDetailUrl);
    return value ? canonical(value) : detailUrl(card);
  }

  function candidateRows() {
    return previewCards().map((card) => ({
      card,
      candidate_id: text(card.dataset.candidateId),
      listing_detail_url: listingDetailUrl(card),
      detail_url: detailUrl(card),
    }));
  }

  function completeCandidateRow(row) {
    return Boolean(row.candidate_id && row.listing_detail_url && row.detail_url);
  }

  function setCardDecision(card, decision) {
    card.dataset.previewDecision = decision;
    card.classList.remove("pending", "confirmed", "rejected");
    card.classList.add(
      decision === "confirmed"
        ? "confirmed"
        : decision === "rejected"
          ? "rejected"
          : "pending",
    );
    const badge = card.querySelector(".badge");
    if (badge) {
      badge.className = `badge ${
        decision === "confirmed"
          ? "confirmed"
          : decision === "rejected"
            ? "rejected"
            : "pending"
      }`;
      badge.textContent = decision === "confirmed"
        ? "real event"
        : decision === "rejected"
          ? "not event"
          : "preview";
    }
    const notice = [...card.querySelectorAll(".snippet")].find((node) =>
      text(node.textContent).startsWith("TEMPORARY PREVIEW"),
    );
    if (notice) {
      notice.textContent = decision === "confirmed"
        ? "SELECTED AS REAL EVENT · Selection is not committed until the List Page review is saved."
        : decision === "rejected"
          ? "SELECTED AS NOT EVENT · This candidate will not be collected."
          : "TEMPORARY PREVIEW · Choose REAL EVENT or NOT EVENT before confirming this List Page.";
    }
  }

  function persistPanelSnapshot() {
    try {
      const snapshot = JSON.parse(sessionStorage.getItem(ACTIVE_PREVIEW_KEY) || "null");
      const container = document.getElementById("event-candidates");
      if (!snapshot || !container) return;
      snapshot.html = container.innerHTML;
      snapshot.count = text(document.getElementById("event-count")?.textContent) || "0";
      snapshot.title = text(document.getElementById("event-candidates-title")?.textContent);
      snapshot.hint = text(document.getElementById("event-candidates-hint")?.textContent);
      sessionStorage.setItem(ACTIVE_PREVIEW_KEY, JSON.stringify(snapshot));
    } catch {
      // The current DOM remains usable when session storage is unavailable.
    }
  }

  function saveOneDecision(url, candidateId, decision) {
    const decisions = decisionsFor(url);
    if (decision === "pending") delete decisions[candidateId];
    else decisions[candidateId] = decision;
    saveDecisions(url, decisions);
    persistPanelSnapshot();
    render(url);
  }

  function actionButton(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `button small ${className}`.trim();
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function installCandidateActions(url, row, storedDecision) {
    setCardDecision(row.card, storedDecision || "pending");
    let actions = row.card.querySelector(".preview-event-review-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "actions preview-event-review-actions";
      row.card.appendChild(actions);
    }
    actions.replaceChildren(
      actionButton("REAL EVENT", "primary", () =>
        saveOneDecision(url, row.candidate_id, "confirmed"),
      ),
      actionButton("NOT EVENT", "reject", () =>
        saveOneDecision(url, row.candidate_id, "rejected"),
      ),
      actionButton("RESET", "secondary", () =>
        saveOneDecision(url, row.candidate_id, "pending"),
      ),
    );
  }

  function encodedReviewPayload(url, card, rows, decisions) {
    const payload = {
      listing_candidate_id: text(card.dataset.candidateId),
      listing_url: canonical(url),
      decisions: rows.map((row) => ({
        candidate_id: row.candidate_id,
        listing_detail_url: row.listing_detail_url,
        detail_url: row.detail_url,
        decision: decisions[row.candidate_id],
      })),
    };
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    let binary = "";
    bytes.forEach((value) => { binary += String.fromCharCode(value); });
    const token = btoa(binary)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    return PROTOCOL_PREFIX + token;
  }

  async function saveListPageReview(url, decision, button) {
    const card = listingCard(url);
    const rows = candidateRows();
    const decisions = decisionsFor(url);
    if (!card || !rows.length || rows.some((row) => !completeCandidateRow(row))) {
      setGlobalStatus(
        "PREVIEW DATA INVALID · Run Preview again before saving this List Page review.",
        "error",
      );
      return;
    }

    const pendingCount = rows.filter(
      (row) => !["confirmed", "rejected"].includes(decisions[row.candidate_id]),
    ).length;
    if (pendingCount) {
      setGlobalStatus(
        `REVIEW REQUIRED · ${pendingCount} PREVIEW CANDIDATE${pendingCount === 1 ? "" : "S"} STILL UNREVIEWED`,
        "error",
      );
      return;
    }

    const realCount = rows.filter(
      (row) => decisions[row.candidate_id] === "confirmed",
    ).length;
    if (decision === "confirmed" && !realCount) {
      setGlobalStatus(
        "A LIST PAGE CANNOT BE CONFIRMED WITHOUT A REAL EVENT SELECTION",
        "error",
      );
      return;
    }
    if (decision === "rejected" && realCount) {
      setGlobalStatus(
        "A REJECTED LIST PAGE CANNOT CONTAIN REAL EVENT SELECTIONS",
        "error",
      );
      return;
    }

    button.disabled = true;
    setGlobalStatus("SAVING PREVIEW EVENT REVIEW", "warn");
    try {
      await request("/api/local-events/review/listing-decision", {
        candidate_id: encodedReviewPayload(url, card, rows, decisions),
        decision,
      });
      await window.InfoScreenReviewStudio?.loadState?.();
      render(url);
      setGlobalStatus(
        decision === "confirmed"
          ? `${realCount} REAL EVENT${realCount === 1 ? "" : "S"} SAVED · LIST PAGE CONFIRMED`
          : "NO REAL EVENTS · LIST PAGE REJECTED",
        decision === "confirmed" ? "ok" : "error",
      );
    } catch (error) {
      setGlobalStatus(text(error?.message || error), "error");
    } finally {
      button.disabled = false;
    }
  }

  function bindListingReviewButtons(url, card) {
    const expected = canonical(url);
    const actions = card?.querySelector(".actions");
    if (!expected || !actions) return;

    const buttons = [...actions.querySelectorAll("button")];
    const buttonByLabel = (label) => buttons.find(
      (button) => text(button.textContent).toUpperCase() === label,
    );

    const bind = (button, decision) => {
      if (!button || button.dataset.previewReviewBound === "true") return;
      button.dataset.previewReviewBound = "true";
      button.addEventListener("click", (event) => {
        if (activePreviewUrl() !== expected) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        void saveListPageReview(expected, decision, button);
      }, true);
    };

    bind(buttonByLabel("CONFIRM LIST PAGE"), "confirmed");
    bind(buttonByLabel("REJECT"), "rejected");
  }

  async function collectSelectedRealEvents(url, button) {
    button.disabled = true;
    setGlobalStatus("COLLECTING SELECTED REAL EVENTS", "warn");
    try {
      const payload = await request("/api/local-events/review/collect-events", {});
      sessionStorage.removeItem(ACTIVE_PREVIEW_KEY);
      clearDecisions(url);
      document.dispatchEvent(new CustomEvent("infoscreen:review-state", {detail: payload}));
      document.getElementById("preview-real-workflow")?.remove();
      await window.InfoScreenReviewStudio?.loadState?.();
      const count = (payload.events || []).filter(
        (row) => canonical(row.listing_url) === canonical(url),
      ).length;
      setGlobalStatus(
        `${count} SELECTED REAL EVENT${count === 1 ? "" : "S"} COLLECTED`,
        count ? "ok" : "error",
      );
    } catch (error) {
      setGlobalStatus(text(error?.message || error), "error");
    } finally {
      button.disabled = false;
    }
  }

  function render(url = activePreviewUrl()) {
    const expected = canonical(url);
    const container = document.getElementById("event-candidates");
    const listing = listingCard(expected);
    const rows = candidateRows();
    if (!expected || !container || !listing || !rows.length) {
      document.getElementById("preview-real-workflow")?.remove();
      return;
    }

    bindListingReviewButtons(expected, listing);

    let workflow = document.getElementById("preview-real-workflow");
    if (!workflow) {
      workflow = document.createElement("div");
      workflow.id = "preview-real-workflow";
      workflow.className = "actions";
      container.before(workflow);
    }
    workflow.replaceChildren();

    const invalidCount = rows.filter((row) => !completeCandidateRow(row)).length;
    if (invalidCount) {
      const title = document.getElementById("event-candidates-title");
      const hint = document.getElementById("event-candidates-hint");
      if (title) title.textContent = "Preview candidates · invalid identity data";
      if (hint) {
        hint.textContent = `${invalidCount} CANDIDATE${invalidCount === 1 ? "" : "S"} MISSING IDENTITY OR DETAIL URL`;
      }
      const explanation = document.createElement("div");
      explanation.className = "snippet";
      explanation.textContent = "PREVIEW DATA INVALID · Re-run Preview before saving this List Page review.";
      workflow.appendChild(explanation);
      return;
    }

    const decisions = decisionsFor(expected);
    rows.forEach((row) => installCandidateActions(
      expected,
      row,
      decisions[row.candidate_id] || "pending",
    ));

    const realCount = rows.filter(
      (row) => decisions[row.candidate_id] === "confirmed",
    ).length;
    const rejectedCount = rows.filter(
      (row) => decisions[row.candidate_id] === "rejected",
    ).length;
    const pendingCount = rows.length - realCount - rejectedCount;

    const title = document.getElementById("event-candidates-title");
    const hint = document.getElementById("event-candidates-hint");
    if (title) title.textContent = "Preview candidates · select real events";
    if (hint) {
      hint.textContent = `${realCount} REAL EVENT · ${rejectedCount} NOT EVENT · ${pendingCount} UNREVIEWED`;
    }

    const explanation = document.createElement("div");
    explanation.className = "snippet";
    explanation.textContent = pendingCount
      ? `REVIEW REQUIRED · Select REAL EVENT or NOT EVENT for all ${rows.length} Preview candidates.`
      : realCount
        ? `${realCount} REAL EVENT${realCount === 1 ? "" : "S"} SELECTED · Confirm the List Page before formal collection.`
        : "NO REAL EVENTS SELECTED · Reject this List Page.";
    workflow.appendChild(explanation);

    if (pendingCount) return;

    const decision = listingDecision(listing);
    if (realCount) {
      workflow.appendChild(actionButton(
        decision === "confirmed"
          ? `UPDATE ${realCount} REAL EVENT SELECTION${realCount === 1 ? "" : "S"}`
          : `CONFIRM ${realCount} REAL EVENT${realCount === 1 ? "" : "S"}`,
        "primary",
        (event) => saveListPageReview(expected, "confirmed", event.currentTarget),
      ));
      if (decision === "confirmed") {
        workflow.appendChild(actionButton(
          `COLLECT ${realCount} SELECTED REAL EVENT${realCount === 1 ? "" : "S"}`,
          "warning",
          (event) => collectSelectedRealEvents(expected, event.currentTarget),
        ));
      }
    } else {
      workflow.appendChild(actionButton(
        "REJECT LIST PAGE · NO REAL EVENTS",
        "reject",
        (event) => saveListPageReview(expected, "rejected", event.currentTarget),
      ));
    }
  }

  document.addEventListener("infoscreen:review-preview", (event) => {
    render(text(event.detail?.url));
  });
  document.addEventListener("infoscreen:review-rendered", () => render());
  document.addEventListener("DOMContentLoaded", () => render());
})();