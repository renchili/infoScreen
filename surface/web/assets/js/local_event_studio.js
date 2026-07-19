"use strict";

(() => {
  const ui = {};
  const state = { sources: [], sourceId: "", listingUrl: "", rules: null, test: null, timer: null };

  const byId = (id) => document.getElementById(id);
  const text = (value, fallback = "—") => String(value ?? "").trim() || fallback;

  async function request(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const payload = await response.json().catch(async () => ({ error: await response.text() }));
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

  function source() {
    return state.sources.find((item) => item.source_id === state.sourceId) || null;
  }

  function populateSources() {
    ui.source.innerHTML = "";
    state.sources.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.source_id;
      option.textContent = item.name || item.source_id;
      ui.source.appendChild(option);
    });
    state.sourceId = state.sources[0]?.source_id || "";
    ui.source.value = state.sourceId;
    populateListings();
  }

  function populateListings() {
    ui.listing.innerHTML = "";
    const items = source()?.listing_urls || [];
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.listing_url;
      option.textContent = item.listing_url;
      ui.listing.appendChild(option);
    });
    state.listingUrl = items[0]?.listing_url || "";
    ui.listing.value = state.listingUrl;
  }

  function fieldLines(fields) {
    if (!fields || typeof fields !== "object") return "—";
    const lines = [];
    for (const name of ["title", "when", "where", "url", "summary", "image"]) {
      const rule = fields[name];
      if (rule?.selector) lines.push(`${name.toUpperCase()}: ${rule.selector}${rule.attribute ? ` @${rule.attribute}` : ""}`);
    }
    return lines.join("\n") || "—";
  }

  function renderRule(payload) {
    state.rules = payload;
    const rule = payload.draft || payload.published;
    if (!rule) {
      setStatus(ui.ruleStatus, "NO DRAFT");
      ui.card.textContent = "—";
      ui.url.textContent = "—";
      ui.listFields.textContent = "—";
      ui.detailFields.textContent = "—";
      return;
    }
    setStatus(
      ui.ruleStatus,
      payload.draft ? "DRAFT SAVED BY LIVE BROWSER" : `PUBLISHED V${rule.version}`,
      payload.draft ? "warn" : "ok",
    );
    ui.card.textContent = rule.card?.selector || "—";
    ui.url.textContent = rule.fields?.url?.selector || "—";
    ui.listFields.textContent = fieldLines(rule.fields);
    ui.detailFields.textContent = rule.detail_page?.enabled ? fieldLines(rule.detail_page.fields) : "disabled";
  }

  function clear(node) {
    while (node.firstChild) node.firstChild.remove();
  }

  function renderRows(node, rows, accepted) {
    clear(node);
    if (!rows?.length) {
      const empty = document.createElement("div");
      empty.className = "message";
      empty.textContent = accepted ? "No confirmed detail pages yet." : "No rejected samples.";
      node.appendChild(empty);
      return;
    }
    rows.slice(0, 20).forEach((row) => {
      const article = document.createElement("article");
      article.className = "result";
      if (accepted) {
        const event = row.event || {};
        const heading = document.createElement("h4");
        const link = document.createElement("a");
        link.href = event.url || "#";
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = text(event.title, "Untitled");
        heading.appendChild(link);
        const body = document.createElement("p");
        body.textContent = `${text(event.when)} · ${text(event.where)}`;
        article.append(heading, body);
      } else {
        const heading = document.createElement("h4");
        heading.textContent = text(row.reason, "rejected");
        const body = document.createElement("p");
        body.textContent = text(row.detail || row.card_text || JSON.stringify(row.values || {}), "");
        article.append(heading, body);
      }
      node.appendChild(article);
    });
  }

  function renderTest(result) {
    state.test = result;
    if (!result) {
      setStatus(ui.testStatus, "NOT VALIDATED");
      ui.matched.textContent = "—";
      ui.accepted.textContent = "—";
      ui.rejected.textContent = "—";
      ui.publishable.textContent = "—";
      ui.publish.disabled = true;
      ui.testMessage.textContent = "Use SAVE CURRENT LISTING STATE in the live browser after mappings are complete.";
      renderRows(ui.acceptedList, [], true);
      renderRows(ui.rejectedList, [], false);
      return;
    }
    ui.matched.textContent = String(result.matched_card_count ?? 0);
    ui.accepted.textContent = String(result.accepted_count ?? 0);
    ui.rejected.textContent = String(result.rejected_count ?? 0);
    ui.publishable.textContent = result.publishable ? "YES" : "NO";
    setStatus(ui.testStatus, result.publishable ? "LIVE DETAIL VALIDATION PASSED" : "VALIDATION FAILED", result.publishable ? "ok" : "error");
    const errors = [...(result.fatal_errors || []), ...(result.warnings || [])];
    ui.testMessage.textContent = errors.length
      ? errors.join(" · ")
      : `Validated by ${result.validation_mode || "live browser"} at ${text(result.tested_at)}`;
    ui.publish.disabled = !result.publishable || !state.rules?.draft;
    renderRows(ui.acceptedList, result.accepted || [], true);
    renderRows(ui.rejectedList, result.rejected || [], false);
  }

  async function loadState() {
    if (!state.sourceId || !state.listingUrl) return;
    try {
      const params = new URLSearchParams({ source_id: state.sourceId, listing_url: state.listingUrl });
      const [rules, latest] = await Promise.all([
        request(`/api/local-events/studio/rules?${params}`),
        request(`/api/local-events/studio/test-latest?${params}`),
      ]);
      renderRule(rules);
      renderTest(latest.result || null);
      setStatus(ui.globalStatus, "READY", "ok");
    } catch (error) {
      setStatus(ui.globalStatus, error.message, "error");
    }
  }

  async function openBrowser() {
    ui.open.disabled = true;
    setStatus(ui.globalStatus, "STARTING REAL CHROMIUM", "warn");
    ui.browserMessage.textContent = "Starting a real browser window on the Surface desktop...";
    try {
      const payload = await request("/api/local-events/studio/capture", {
        method: "POST",
        body: JSON.stringify({ source_id: state.sourceId, listing_url: state.listingUrl }),
      });
      const session = payload.session || payload.snapshot?.session || {};
      ui.browserMessage.textContent = session.already_running
        ? "The live browser is already open. Continue in that window."
        : "A real Chromium window was started. Use the InfoScreen toolbar inside the official website.";
      setStatus(ui.globalStatus, "LIVE BROWSER OPEN", "ok");
      window.setTimeout(loadState, 1200);
    } catch (error) {
      ui.browserMessage.textContent = error.message;
      setStatus(ui.globalStatus, "BROWSER START FAILED", "error");
    } finally {
      ui.open.disabled = false;
    }
  }

  async function publish() {
    ui.publish.disabled = true;
    try {
      await request("/api/local-events/studio/publish", {
        method: "POST",
        body: JSON.stringify({ source_id: state.sourceId, listing_url: state.listingUrl }),
      });
      ui.testMessage.textContent = "Published. Run Local Events below.";
      await loadState();
    } catch (error) {
      ui.testMessage.textContent = error.message;
      ui.publish.disabled = false;
    }
  }

  function renderProduction(payload) {
    clear(ui.results);
    const rows = Array.isArray(payload.results) ? payload.results : [];
    ui.runMessage.textContent = `${rows.length} activities · partial=${Boolean(payload.partial)} · completed=${payload.completed_source_count ?? "—"} · incomplete=${payload.incomplete_source_count ?? "—"}`;
    rows.slice(0, 80).forEach((event) => {
      const article = document.createElement("article");
      article.className = "result";
      const heading = document.createElement("h4");
      const link = document.createElement("a");
      link.href = event.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = text(event.title, "Untitled");
      heading.appendChild(link);
      const body = document.createElement("p");
      body.textContent = `${text(event.when)} · ${text(event.where)} · ${text(event.source_name || event.host)}`;
      article.append(heading, body);
      ui.results.appendChild(article);
    });
  }

  async function runProduction() {
    ui.run.disabled = true;
    setStatus(ui.runStatus, "RUNNING", "warn");
    try {
      const payload = await request("/api/local-events/search", {
        method: "POST",
        body: JSON.stringify({ location: ui.location.value.trim() || "Punggol Singapore" }),
      });
      renderProduction(payload);
      setStatus(ui.runStatus, "COMPLETE", "ok");
    } catch (error) {
      ui.runMessage.textContent = error.message;
      setStatus(ui.runStatus, "FAILED", "error");
    } finally {
      ui.run.disabled = false;
    }
  }

  async function initialize() {
    Object.assign(ui, {
      globalStatus: byId("global-status"), source: byId("source-select"), listing: byId("listing-select"),
      open: byId("open-browser"), reload: byId("reload-state"), browserMessage: byId("browser-message"),
      ruleStatus: byId("rule-status"), card: byId("card-selector"), url: byId("url-selector"),
      listFields: byId("listing-fields"), detailFields: byId("detail-fields"),
      testStatus: byId("test-status"), matched: byId("matched"), accepted: byId("accepted"),
      rejected: byId("rejected"), publishable: byId("publishable"), testMessage: byId("test-message"),
      acceptedList: byId("accepted-list"), rejectedList: byId("rejected-list"), publish: byId("publish"),
      runStatus: byId("run-status"), location: byId("location"), run: byId("run"),
      runMessage: byId("run-message"), results: byId("results"),
    });

    ui.source.addEventListener("change", async () => {
      state.sourceId = ui.source.value;
      populateListings();
      await loadState();
    });
    ui.listing.addEventListener("change", async () => {
      state.listingUrl = ui.listing.value;
      await loadState();
    });
    ui.open.addEventListener("click", openBrowser);
    ui.reload.addEventListener("click", loadState);
    ui.publish.addEventListener("click", publish);
    ui.run.addEventListener("click", runProduction);

    try {
      const payload = await request("/api/local-events/studio/sources");
      state.sources = payload.sources || [];
      populateSources();
      await loadState();
      state.timer = window.setInterval(loadState, 2500);
    } catch (error) {
      setStatus(ui.globalStatus, error.message, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", initialize);
})();
