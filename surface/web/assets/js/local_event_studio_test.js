"use strict";

(() => {
  const FIELD_NAMES = ["title", "when", "where", "url", "summary", "image"];
  const DETAIL_FIELD_NAMES = ["title", "when", "where", "summary", "image"];
  const ui = {};
  let testIsCurrent = false;

  function byId(id) {
    return document.getElementById(id);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail ? `: ${payload.detail}` : "";
      throw new Error(`${payload.error || `HTTP ${response.status}`}${detail}`);
    }
    return payload;
  }

  function query(params) {
    return new URLSearchParams(params).toString();
  }

  function binding() {
    return {
      source_id: ui.sourceSelect.value,
      listing_url: ui.listingSelect.value,
    };
  }

  function snapshotId() {
    return ui.snapshotSelect.value;
  }

  function selectorRule(name, input, detail = false) {
    const selector = input.value.trim();
    if (!selector) return null;
    const rule = { selector };
    if (!detail && name === "url") rule.attribute = "href";
    if (name === "image") rule.attribute = "src";
    if (name === "summary" || name === "image") rule.optional = true;
    if (name === "where") {
      rule.allow_source_default = detail ? false : ui.allowSourceDefault.checked;
    }
    return rule;
  }

  function buildDraftPayload() {
    const current = binding();
    const payload = {
      schema_version: 1,
      source_id: current.source_id,
      listing_url: current.listing_url,
      version: 0,
      status: "draft",
      fields: {},
      detail_page: { enabled: ui.detailEnabled.checked, fields: {} },
      validation: {
        require_public_detail_url: true,
        require_current_or_future_date: true,
      },
    };

    const cardSelector = ui.cardSelector.value.trim();
    if (cardSelector) {
      payload.card = {
        selector: cardSelector,
        exclude_selectors: ui.excludeSelectors.value
          .split("\n")
          .map((value) => value.trim())
          .filter((value, index, values) => value && values.indexOf(value) === index),
      };
    }

    for (const name of FIELD_NAMES) {
      const input = document.querySelector(`[data-field="${name}"]`);
      const rule = selectorRule(name, input);
      if (rule) payload.fields[name] = rule;
    }
    if (payload.detail_page.enabled) {
      for (const name of DETAIL_FIELD_NAMES) {
        const input = document.querySelector(`[data-detail-field="${name}"]`);
        const rule = selectorRule(name, input, true);
        if (rule) payload.detail_page.fields[name] = rule;
      }
    }
    return payload;
  }

  function setGlobalStatus(message, kind = "") {
    ui.globalStatus.textContent = message;
    ui.globalStatus.className = `status ${kind}`.trim();
  }

  function setTestState(message, kind = "") {
    ui.testState.textContent = message;
    ui.testState.className = `status ${kind}`.trim();
  }

  function clearNode(node) {
    while (node.firstChild) node.firstChild.remove();
  }

  function appendTextRow(parent, label, value) {
    const row = document.createElement("div");
    const term = document.createElement("span");
    const data = document.createElement("strong");
    term.textContent = label;
    data.textContent = value || "—";
    row.append(term, data);
    parent.appendChild(row);
  }

  function evidenceDetails(evidence) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const pre = document.createElement("pre");
    summary.textContent = "FIELD EVIDENCE";
    pre.textContent = JSON.stringify(evidence || {}, null, 2);
    details.append(summary, pre);
    return details;
  }

  function renderAccepted(rows) {
    clearNode(ui.acceptedPreview);
    if (!rows.length) {
      ui.acceptedPreview.textContent = "No accepted events.";
      return;
    }
    for (const row of rows) {
      const item = document.createElement("article");
      item.className = "preview-item accepted-item";
      const title = document.createElement("h4");
      title.textContent = row.event?.title || "Untitled event";
      const values = document.createElement("div");
      values.className = "preview-values";
      appendTextRow(values, "WHEN", row.event?.when);
      appendTextRow(values, "WHERE", row.event?.where);
      appendTextRow(values, "URL", row.event?.url);
      appendTextRow(values, "SUMMARY", row.event?.summary);
      item.append(title, values, evidenceDetails(row.evidence));
      ui.acceptedPreview.appendChild(item);
    }
  }

  function renderRejected(rows) {
    clearNode(ui.rejectedPreview);
    if (!rows.length) {
      ui.rejectedPreview.textContent = "No rejected cards.";
      return;
    }
    for (const row of rows) {
      const item = document.createElement("article");
      item.className = "preview-item rejected-item";
      const title = document.createElement("h4");
      title.textContent = row.reason || "rejected";
      const text = document.createElement("p");
      text.textContent = row.card_text || row.values?.title || row.card_id || "";
      const reasons = document.createElement("code");
      reasons.textContent = (row.reasons || [row.reason]).filter(Boolean).join(" · ");
      item.append(title, text, reasons, evidenceDetails(row.evidence));
      ui.rejectedPreview.appendChild(item);
    }
  }

  function renderMessages(result) {
    clearNode(ui.testMessages);
    const messages = [
      ...(result.fatal_errors || []).map((value) => ({ kind: "error", value })),
      ...(result.warnings || []).map((value) => ({ kind: "warn", value })),
    ];
    if (!messages.length) {
      const message = document.createElement("div");
      message.className = "test-message ok";
      message.textContent = "No fatal validation errors.";
      ui.testMessages.appendChild(message);
      return;
    }
    for (const entry of messages) {
      const message = document.createElement("div");
      message.className = `test-message ${entry.kind}`;
      message.textContent = entry.value;
      ui.testMessages.appendChild(message);
    }
  }

  function renderResult(result, { current = true } = {}) {
    if (!result) {
      testIsCurrent = false;
      ui.testEmpty.classList.remove("hidden");
      ui.testResult.classList.add("hidden");
      setTestState("NOT TESTED");
      return;
    }
    testIsCurrent = current;
    ui.testEmpty.classList.add("hidden");
    ui.testResult.classList.remove("hidden");
    ui.testMatched.textContent = String(result.matched_card_count || 0);
    ui.testAccepted.textContent = String(result.accepted_count || 0);
    ui.testRejected.textContent = String(result.rejected_count || 0);
    ui.testPublishable.textContent = result.publishable ? "YES" : "NO";
    ui.testPublishable.className = result.publishable ? "ok-text" : "error-text";
    if (!current) {
      setTestState("STALE · RETEST REQUIRED", "warn");
    } else if (result.publishable) {
      setTestState("PUBLISHABLE", "ok");
    } else {
      setTestState("FAILED", "error");
    }
    renderMessages(result);
    renderAccepted(result.accepted || []);
    renderRejected(result.rejected || []);
  }

  function markTestStale() {
    if (!ui.testResult.classList.contains("hidden")) {
      testIsCurrent = false;
      setTestState("STALE · RETEST REQUIRED", "warn");
    }
  }

  async function saveDraft() {
    const payload = await api("/api/local-events/studio/draft", {
      method: "PUT",
      body: JSON.stringify(buildDraftPayload()),
    });
    return payload.rule;
  }

  async function runTest({ save = true } = {}) {
    const selectedSnapshot = snapshotId();
    if (!selectedSnapshot) throw new Error("Capture or select a snapshot before testing");
    ui.testDraftButton.disabled = true;
    setGlobalStatus("TESTING DRAFT");
    try {
      if (save) await saveDraft();
      const payload = await api("/api/local-events/studio/test", {
        method: "POST",
        body: JSON.stringify({ ...binding(), snapshot_id: selectedSnapshot }),
      });
      renderResult(payload.result, { current: true });
      setGlobalStatus(
        payload.result.publishable ? "DRAFT TEST PASSED" : "DRAFT TEST FAILED",
        payload.result.publishable ? "ok" : "error",
      );
      return payload.result;
    } finally {
      ui.testDraftButton.disabled = false;
    }
  }

  async function publishTestedDraft(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!window.confirm("Test the selected snapshot and publish this draft when it passes?")) return;
    ui.publishButton.disabled = true;
    try {
      const result = await runTest({ save: true });
      if (!result.publishable) throw new Error("Draft test is not publishable");
      const payload = await api("/api/local-events/studio/publish", {
        method: "POST",
        body: JSON.stringify(binding()),
      });
      setGlobalStatus(`PUBLISHED V${payload.rule.version}`, "ok");
      setTestState(`PUBLISHED FROM ${result.run_id}`, "ok");
      testIsCurrent = true;
    } catch (error) {
      setGlobalStatus(error.message || String(error), "error");
    } finally {
      ui.publishButton.disabled = false;
    }
  }

  async function loadLatestTest() {
    const current = binding();
    if (!current.source_id || !current.listing_url) return renderResult(null);
    const payload = await api(`/api/local-events/studio/test-latest?${query(current)}`);
    renderResult(payload.result, { current: false });
  }

  async function loadLatestWhenBindingReady(attempt = 0) {
    const current = binding();
    if (!current.source_id || !current.listing_url) {
      if (attempt >= 50) {
        renderResult(null);
        return;
      }
      window.setTimeout(() => {
        loadLatestWhenBindingReady(attempt + 1).catch(() => renderResult(null));
      }, 100);
      return;
    }
    await loadLatestTest();
  }

  function bind() {
    Object.assign(ui, {
      globalStatus: byId("global-status"),
      sourceSelect: byId("source-select"),
      listingSelect: byId("listing-select"),
      snapshotSelect: byId("snapshot-select"),
      cardSelector: byId("card-selector"),
      excludeSelectors: byId("exclude-selectors"),
      allowSourceDefault: byId("allow-source-default"),
      detailEnabled: byId("detail-enabled"),
      testDraftButton: byId("test-draft-button"),
      publishButton: byId("publish-button"),
      testState: byId("test-state"),
      testEmpty: byId("test-empty"),
      testResult: byId("test-result"),
      testMatched: byId("test-matched"),
      testAccepted: byId("test-accepted"),
      testRejected: byId("test-rejected"),
      testPublishable: byId("test-publishable"),
      testMessages: byId("test-messages"),
      acceptedPreview: byId("accepted-preview"),
      rejectedPreview: byId("rejected-preview"),
      editorPanel: document.querySelector(".editor-panel"),
    });

    ui.testDraftButton.addEventListener("click", () => {
      runTest({ save: true }).catch((error) => setGlobalStatus(error.message || String(error), "error"));
    });
    ui.publishButton.addEventListener("click", publishTestedDraft, true);
    ui.editorPanel.addEventListener("input", markTestStale);
    ui.editorPanel.addEventListener("change", markTestStale);
    ui.sourceSelect.addEventListener("change", () => setTimeout(() => loadLatestTest().catch(() => renderResult(null)), 0));
    ui.listingSelect.addEventListener("change", () => setTimeout(() => loadLatestTest().catch(() => renderResult(null)), 0));
    ui.snapshotSelect.addEventListener("change", markTestStale);
    setTimeout(() => loadLatestWhenBindingReady().catch(() => renderResult(null)), 0);
  }

  document.addEventListener("DOMContentLoaded", bind);
})();
