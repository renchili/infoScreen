"use strict";

(() => {
  const ACTIVE_PREVIEW_KEY = "infoscreen.review.active-preview-panel";
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

  function activePreviewUrl() {
    try {
      const value = JSON.parse(sessionStorage.getItem(ACTIVE_PREVIEW_KEY) || "null");
      return canonical(value?.url || "");
    } catch {
      return "";
    }
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

  function removeActions() {
    document.getElementById("preview-real-workflow")?.remove();
  }

  function actionButton(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `button small ${className}`.trim();
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  async function setListingDecision(url, decision, button) {
    const card = listingCard(url);
    const candidateId = text(card?.dataset.candidateId);
    if (!candidateId) {
      setGlobalStatus("LIST PAGE CANDIDATE IS NOT AVAILABLE IN THE CURRENT REVIEW STATE", "error");
      return;
    }

    button.disabled = true;
    setGlobalStatus(
      decision === "confirmed" ? "CONFIRMING LIST PAGE" : "SAVING LIST PAGE DECISION",
      "warn",
    );
    try {
      await request("/api/local-events/review/listing-decision", {
        candidate_id: candidateId,
        decision,
      });
      await window.InfoScreenReviewStudio?.loadState?.();
      render(url);
      setGlobalStatus(
        decision === "confirmed"
          ? "LIST PAGE CONFIRMED · COLLECT REAL EVENTS WHEN READY"
          : `LIST PAGE ${decision.toUpperCase()}`,
        decision === "rejected" ? "error" : "ok",
      );
    } catch (error) {
      setGlobalStatus(text(error?.message || error), "error");
    } finally {
      button.disabled = false;
    }
  }

  async function collectRealEvents(url, button) {
    button.disabled = true;
    setGlobalStatus("COLLECTING REAL EVENTS FROM CONFIRMED LIST PAGES", "warn");
    try {
      const payload = await request("/api/local-events/review/collect-events", {});
      sessionStorage.removeItem(ACTIVE_PREVIEW_KEY);
      document.dispatchEvent(new CustomEvent("infoscreen:review-state", {detail: payload}));
      removeActions();
      await window.InfoScreenReviewStudio?.loadState?.();

      const sourceId = text(listingCard(url)?.dataset.sourceId);
      const count = (payload.events || []).filter(
        (row) => !sourceId || text(row.source_id) === sourceId,
      ).length;
      setGlobalStatus(
        `${count} REAL EVENT CANDIDATE${count === 1 ? "" : "S"} READY FOR REVIEW`,
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
    const card = listingCard(expected);
    if (!expected || !container || !card || !container.querySelector('[data-preview="true"]')) {
      removeActions();
      return;
    }

    let actions = document.getElementById("preview-real-workflow");
    if (!actions) {
      actions = document.createElement("div");
      actions.id = "preview-real-workflow";
      actions.className = "actions";
      container.before(actions);
    }
    actions.replaceChildren();

    const decision = listingDecision(card);
    const explanation = document.createElement("div");
    explanation.className = "snippet";
    explanation.textContent = decision === "confirmed"
      ? "LIST PAGE CONFIRMED · Run formal collection to create saved Event candidates with review actions."
      : decision === "rejected"
        ? "LIST PAGE REJECTED · This Preview remains temporary and will not be collected."
        : "PREVIEW COMPLETE · Confirm this List Page to make it eligible for formal Event collection.";
    actions.appendChild(explanation);

    if (decision !== "confirmed") {
      actions.appendChild(actionButton("CONFIRM LIST PAGE", "primary", (event) =>
        setListingDecision(expected, "confirmed", event.currentTarget),
      ));
    }
    if (decision === "confirmed") {
      actions.appendChild(actionButton("COLLECT REAL EVENTS", "warning", (event) =>
        collectRealEvents(expected, event.currentTarget),
      ));
      actions.appendChild(actionButton("RESET TO PENDING", "secondary", (event) =>
        setListingDecision(expected, "pending", event.currentTarget),
      ));
    } else if (decision === "pending") {
      actions.appendChild(actionButton("REJECT LIST PAGE", "reject", (event) =>
        setListingDecision(expected, "rejected", event.currentTarget),
      ));
    } else {
      actions.appendChild(actionButton("RESET TO PENDING", "secondary", (event) =>
        setListingDecision(expected, "pending", event.currentTarget),
      ));
    }
  }

  document.addEventListener("infoscreen:review-preview", (event) => {
    render(text(event.detail?.url));
  });
  document.addEventListener("infoscreen:review-rendered", () => render());
  document.addEventListener("infoscreen:review-state", removeActions);
  document.addEventListener("DOMContentLoaded", () => render());
})();
