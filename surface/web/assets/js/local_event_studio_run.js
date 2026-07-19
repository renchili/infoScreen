"use strict";

(() => {
  const DEFAULT_LOCATION = "Punggol Singapore";
  const REQUIRED_FIELDS = ["title", "when", "where", "url"];
  const ui = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function setProductionStatus(message, kind = "") {
    ui.productionStatus.textContent = message;
    ui.productionStatus.className = `status ${kind}`.trim();
  }

  async function requestJson(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { ok: response.ok, error: await response.text() };
    return { response, payload };
  }

  function text(value, fallback = "—") {
    const normalized = String(value ?? "").trim();
    return normalized || fallback;
  }

  function clear(node) {
    while (node.firstChild) node.firstChild.remove();
  }

  function appendDefinition(list, label, value) {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const data = document.createElement("dd");
    term.textContent = label;
    data.textContent = text(value);
    row.append(term, data);
    list.appendChild(row);
  }

  function renderEvent(event) {
    const article = document.createElement("article");
    article.className = "production-event";

    const heading = document.createElement("h3");
    const url = String(event.url || "").trim();
    if (url.startsWith("http://") || url.startsWith("https://")) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = text(event.title, "Untitled activity");
      heading.appendChild(link);
    } else {
      heading.textContent = text(event.title, "Untitled activity");
    }

    const values = document.createElement("dl");
    appendDefinition(values, "WHEN", event.when);
    appendDefinition(values, "WHERE", event.where);
    appendDefinition(values, "SOURCE", event.source_name || event.host || event.source_id);
    appendDefinition(values, "POLICY", event.candidate_policy);
    article.append(heading, values);
    return article;
  }

  function resultMessage(payload, httpOk) {
    const sourceStatus = payload.source_status_counts && typeof payload.source_status_counts === "object"
      ? Object.entries(payload.source_status_counts)
        .map(([name, count]) => `${name}=${count}`)
        .join(", ")
      : "";
    const parts = [];
    if (!httpOk) parts.push(text(payload.error, "Local Events request failed"));
    if (payload.write_policy) parts.push(`write_policy=${payload.write_policy}`);
    if (sourceStatus) parts.push(`sources: ${sourceStatus}`);
    if (payload.stderr) parts.push(String(payload.stderr).trim().slice(-600));
    if (!parts.length) parts.push("Production result loaded from surface/.env/local_event_search_results.json.");
    return parts.join(" · ");
  }

  function renderProduction(payload, { httpOk = true, ranNow = false } = {}) {
    const results = Array.isArray(payload.results)
      ? payload.results.filter((item) => item && typeof item === "object")
      : [];
    ui.productionCount.textContent = String(Number(payload.count ?? results.length));
    ui.productionPartial.textContent = payload.partial ? "YES" : "NO";
    ui.productionCompleted.textContent = String(payload.completed_source_count ?? "—");
    ui.productionIncomplete.textContent = String(payload.incomplete_source_count ?? "—");
    ui.productionMessage.textContent = resultMessage(payload, httpOk);
    ui.productionMessage.className = `production-message ${httpOk && payload.ok !== false ? "ok" : "error"}`;

    clear(ui.productionResults);
    for (const event of results.slice(0, 60)) {
      ui.productionResults.appendChild(renderEvent(event));
    }
    if (!results.length) {
      const empty = document.createElement("div");
      empty.className = "production-message";
      empty.textContent = "No production activities are present in the current runtime result.";
      ui.productionResults.appendChild(empty);
    }

    if (httpOk && payload.ok !== false) {
      setProductionStatus(ranNow ? "RUN COMPLETE" : "CURRENT RESULT LOADED", "ok");
    } else {
      setProductionStatus(ranNow ? "RUN FAILED" : "CURRENT RESULT UNAVAILABLE", "error");
    }
    updateWorkflowState();
  }

  async function loadCurrentProduction() {
    setProductionStatus("LOADING CURRENT RESULT");
    try {
      const { response, payload } = await requestJson("/api/local-events/search", {
        headers: { Accept: "application/json" },
      });
      renderProduction(payload, { httpOk: response.ok, ranNow: false });
    } catch (error) {
      ui.productionMessage.textContent = error.message || String(error);
      ui.productionMessage.className = "production-message error";
      setProductionStatus("CURRENT RESULT UNAVAILABLE", "error");
    }
  }

  async function runProduction() {
    const location = ui.productionLocation.value.trim() || DEFAULT_LOCATION;
    ui.productionLocation.value = location;
    window.localStorage.setItem("local_events_location", location);
    ui.runButton.disabled = true;
    setProductionStatus("RUNNING · MAY TAKE SEVERAL MINUTES", "warn");
    ui.productionMessage.textContent = "The existing Local Events producer is running. Keep this page open until the request completes.";
    ui.productionMessage.className = "production-message";
    try {
      const { response, payload } = await requestJson("/api/local-events/search", {
        method: "POST",
        body: JSON.stringify({ location }),
      });
      renderProduction(payload, { httpOk: response.ok, ranNow: true });
    } catch (error) {
      ui.productionMessage.textContent = error.message || String(error);
      ui.productionMessage.className = "production-message error";
      setProductionStatus("RUN FAILED", "error");
    } finally {
      ui.runButton.disabled = false;
    }
  }

  function requiredFieldsMapped() {
    return REQUIRED_FIELDS.every((name) => {
      const input = document.querySelector(`[data-field="${name}"]`);
      return Boolean(input && input.value.trim());
    });
  }

  function currentWorkflowStep() {
    if (!ui.snapshotSelect.value) return 1;
    if (!ui.cardSelector.value.trim()) return 2;
    if (!requiredFieldsMapped()) return 3;
    const testState = ui.testState.textContent.trim().toUpperCase();
    const ruleState = ui.ruleState.textContent.trim().toUpperCase();
    if (!testState.includes("PUBLISHABLE") && !testState.startsWith("PUBLISHED")) return 4;
    if (!ruleState.startsWith("PUBLISHED") && !testState.startsWith("PUBLISHED")) return 5;
    return 6;
  }

  function workflowLabel(step) {
    return {
      1: "1 · CAPTURE PAGE",
      2: "2 · SELECT ACTIVITY CARDS",
      3: "3 · MAP REQUIRED FIELDS",
      4: "4 · TEST AND INSPECT",
      5: "5 · PUBLISH TESTED DRAFT",
      6: "6 · RUN AND INSPECT PRODUCTION",
    }[step];
  }

  function updateWorkflowState() {
    const step = currentWorkflowStep();
    ui.workflowState.textContent = workflowLabel(step);
    document.querySelectorAll("[data-workflow-step]").forEach((item) => {
      const itemStep = Number(item.dataset.workflowStep);
      item.classList.toggle("active", itemStep === step);
      item.classList.toggle("complete", itemStep < step);
    });
  }

  function bindWorkflowObservers() {
    const observed = [ui.globalStatus, ui.ruleState, ui.testState];
    const observer = new MutationObserver(updateWorkflowState);
    for (const node of observed) observer.observe(node, { childList: true, subtree: true, characterData: true });
    document.addEventListener("input", updateWorkflowState);
    document.addEventListener("change", updateWorkflowState);
  }

  function initialize() {
    Object.assign(ui, {
      workflowState: byId("workflow-state"),
      globalStatus: byId("global-status"),
      ruleState: byId("rule-state"),
      testState: byId("test-state"),
      snapshotSelect: byId("snapshot-select"),
      cardSelector: byId("card-selector"),
      productionStatus: byId("production-status"),
      productionLocation: byId("production-location"),
      runButton: byId("run-local-events-button"),
      productionCount: byId("production-count"),
      productionPartial: byId("production-partial"),
      productionCompleted: byId("production-completed"),
      productionIncomplete: byId("production-incomplete"),
      productionMessage: byId("production-message"),
      productionResults: byId("production-results"),
    });

    ui.productionLocation.value = window.localStorage.getItem("local_events_location") || DEFAULT_LOCATION;
    ui.runButton.addEventListener("click", runProduction);
    bindWorkflowObservers();
    updateWorkflowState();
    loadCurrentProduction();
  }

  document.addEventListener("DOMContentLoaded", initialize);
})();
