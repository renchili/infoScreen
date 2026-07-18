"use strict";

(() => {
  const FIELD_NAMES = ["title", "when", "where", "url", "summary", "image"];
  const DETAIL_FIELD_NAMES = ["title", "when", "where", "summary", "image"];
  const state = {
    sources: [],
    sourceId: "",
    listingUrl: "",
    snapshots: [],
    snapshot: null,
    dom: null,
    elements: [],
    elementsById: new Map(),
    activeTarget: "card",
    hoverId: null,
    selectedId: null,
    cardExampleIds: [],
    fieldEvidence: {},
    dragging: false,
    dragStart: null,
    dragCurrent: null,
    loadedRuleState: null,
  };

  const ui = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function setStatus(message, kind = "") {
    ui.globalStatus.textContent = message;
    ui.globalStatus.className = `status ${kind}`.trim();
  }

  function setRuleState(message, kind = "") {
    ui.ruleState.textContent = message;
    ui.ruleState.className = `status ${kind}`.trim();
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
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { ok: response.ok, text: await response.text() };
    if (!response.ok) {
      const detail = payload.detail ? `: ${payload.detail}` : "";
      throw new Error(`${payload.error || `HTTP ${response.status}`}${detail}`);
    }
    return payload;
  }

  function query(params) {
    return new URLSearchParams(params).toString();
  }

  function selectedSource() {
    return state.sources.find((source) => source.source_id === state.sourceId) || null;
  }

  function selectedListingState() {
    const source = selectedSource();
    return source
      ? source.listing_urls.find((item) => item.listing_url === state.listingUrl) || null
      : null;
  }

  function sourceName() {
    return selectedSource()?.name || state.sourceId || "source";
  }

  function renderFieldEditors() {
    ui.fieldEditor.innerHTML = "";
    for (const name of FIELD_NAMES) {
      const row = document.createElement("div");
      row.className = "field-row";
      row.innerHTML = `
        <label>
          <span class="field-label">${name.toUpperCase()}</span>
          <input type="text" data-field="${name}" autocomplete="off" spellcheck="false" aria-label="${name} selector" />
        </label>
        <button type="button" class="field-clear" data-clear-field="${name}" aria-label="Clear ${name} selector">×</button>
      `;
      ui.fieldEditor.appendChild(row);
    }

    ui.detailFields.innerHTML = "";
    for (const name of DETAIL_FIELD_NAMES) {
      const row = document.createElement("div");
      row.className = "field-row";
      row.innerHTML = `
        <label>
          <span class="field-label">${name.toUpperCase()}</span>
          <input type="text" data-detail-field="${name}" autocomplete="off" spellcheck="false" aria-label="Detail ${name} selector" />
        </label>
        <button type="button" class="field-clear" data-clear-detail-field="${name}" aria-label="Clear detail ${name} selector">×</button>
      `;
      ui.detailFields.appendChild(row);
    }
  }

  function bindUi() {
    Object.assign(ui, {
      globalStatus: byId("global-status"),
      sourceSelect: byId("source-select"),
      listingSelect: byId("listing-select"),
      snapshotSelect: byId("snapshot-select"),
      captureButton: byId("capture-button"),
      reloadButton: byId("reload-button"),
      viewerEmpty: byId("viewer-empty"),
      imageStage: byId("image-stage"),
      pageImage: byId("page-image"),
      canvas: byId("annotation-canvas"),
      showAllElements: byId("show-all-elements"),
      inspectId: byId("inspect-id"),
      inspectTag: byId("inspect-tag"),
      inspectSelector: byId("inspect-selector"),
      inspectValue: byId("inspect-value"),
      inspectRect: byId("inspect-rect"),
      ruleState: byId("rule-state"),
      cardExampleCount: byId("card-example-count"),
      cardSelector: byId("card-selector"),
      cardMatchCount: byId("card-match-count"),
      excludeSelectors: byId("exclude-selectors"),
      clearCardExamples: byId("clear-card-examples"),
      fieldEditor: byId("field-editor"),
      allowSourceDefault: byId("allow-source-default"),
      detailEnabled: byId("detail-enabled"),
      detailFields: byId("detail-fields"),
      saveDraftButton: byId("save-draft-button"),
      publishButton: byId("publish-button"),
      exportButton: byId("export-button"),
      importInput: byId("import-input"),
      historySelect: byId("history-select"),
      rollbackButton: byId("rollback-button"),
      fieldEvidence: byId("field-evidence"),
    });
    renderFieldEditors();
  }

  function fieldInput(name) {
    return ui.fieldEditor.querySelector(`[data-field="${name}"]`);
  }

  function detailFieldInput(name) {
    return ui.detailFields.querySelector(`[data-detail-field="${name}"]`);
  }

  function resetViewer() {
    state.snapshot = null;
    state.dom = null;
    state.elements = [];
    state.elementsById = new Map();
    state.hoverId = null;
    state.selectedId = null;
    state.cardExampleIds = [];
    state.fieldEvidence = {};
    ui.pageImage.removeAttribute("src");
    ui.imageStage.classList.add("hidden");
    ui.viewerEmpty.classList.remove("hidden");
    updateInspector(null);
    updateCardExamples();
    drawOverlay();
  }

  async function initialize() {
    bindUi();
    bindEvents();
    setStatus("LOADING SOURCES");
    try {
      const payload = await api("/api/local-events/studio/sources");
      state.sources = payload.sources || [];
      populateSourceSelect();
      if (!state.sources.length) {
        setStatus("NO CONFIGURED SOURCES", "warn");
        return;
      }
      state.sourceId = state.sources[0].source_id;
      ui.sourceSelect.value = state.sourceId;
      populateListingSelect();
      await loadContext();
      setStatus("READY", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function populateSourceSelect() {
    ui.sourceSelect.innerHTML = "";
    for (const source of state.sources) {
      const option = document.createElement("option");
      option.value = source.source_id;
      option.textContent = source.name || source.source_id;
      ui.sourceSelect.appendChild(option);
    }
  }

  function populateListingSelect() {
    const source = selectedSource();
    ui.listingSelect.innerHTML = "";
    for (const item of source?.listing_urls || []) {
      const option = document.createElement("option");
      option.value = item.listing_url;
      option.textContent = item.listing_url;
      ui.listingSelect.appendChild(option);
    }
    state.listingUrl = source?.listing_urls?.[0]?.listing_url || "";
    ui.listingSelect.value = state.listingUrl;
  }

  async function loadContext({ preserveSnapshot = false } = {}) {
    if (!state.sourceId || !state.listingUrl) return;
    const previousSnapshotId = preserveSnapshot ? state.snapshot?.snapshot_id : null;
    setStatus("LOADING LOCAL STATE");
    const params = { source_id: state.sourceId, listing_url: state.listingUrl };
    const [rules, snapshots] = await Promise.all([
      api(`/api/local-events/studio/rules?${query(params)}`),
      api(`/api/local-events/studio/snapshots?${query(params)}`),
    ]);
    state.loadedRuleState = rules;
    state.snapshots = snapshots.snapshots || [];
    applyRuleToEditor(rules.draft || rules.published || null);
    renderHistory(rules.history || [], rules.published);
    populateSnapshotSelect(previousSnapshotId);
    const nextSnapshotId = previousSnapshotId && state.snapshots.some((item) => item.snapshot_id === previousSnapshotId)
      ? previousSnapshotId
      : state.snapshots[0]?.snapshot_id;
    if (nextSnapshotId) {
      ui.snapshotSelect.value = nextSnapshotId;
      await loadSnapshot(nextSnapshotId);
    } else {
      resetViewer();
    }
    setStatus("READY", "ok");
  }

  function populateSnapshotSelect(preferredId = null) {
    ui.snapshotSelect.innerHTML = "";
    if (!state.snapshots.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No snapshots captured";
      ui.snapshotSelect.appendChild(option);
      ui.snapshotSelect.disabled = true;
      return;
    }
    ui.snapshotSelect.disabled = false;
    for (const snapshot of state.snapshots) {
      const option = document.createElement("option");
      option.value = snapshot.snapshot_id;
      const captured = new Date(snapshot.captured_at).toLocaleString();
      option.textContent = `${captured} · ${snapshot.page_title || snapshot.snapshot_id}`;
      ui.snapshotSelect.appendChild(option);
    }
    ui.snapshotSelect.value = preferredId || state.snapshots[0].snapshot_id;
  }

  function snapshotAssetUrl(snapshot, asset) {
    return `/api/local-events/studio/snapshot-asset?${query({
      source_id: snapshot.source_id,
      snapshot_id: snapshot.snapshot_id,
      asset,
    })}`;
  }

  async function loadSnapshot(snapshotId) {
    const snapshot = state.snapshots.find((item) => item.snapshot_id === snapshotId);
    if (!snapshot) {
      resetViewer();
      return;
    }
    setStatus("LOADING SNAPSHOT");
    const dom = await api(snapshotAssetUrl(snapshot, "dom.json"), {
      headers: { Accept: "application/json" },
    });
    state.snapshot = snapshot;
    state.dom = dom;
    state.elements = Array.isArray(dom.elements) ? dom.elements : [];
    state.elementsById = new Map(state.elements.map((item) => [item.id, item]));
    state.hoverId = null;
    state.selectedId = null;
    state.cardExampleIds = [];
    state.fieldEvidence = {};
    ui.viewerEmpty.classList.add("hidden");
    ui.imageStage.classList.remove("hidden");
    ui.pageImage.src = snapshotAssetUrl(snapshot, "page.png");
    ui.pageImage.alt = `Captured listing page for ${snapshot.source_name || snapshot.source_id}`;
    updateInspector(null);
    updateCardExamples();
    ui.pageImage.onload = () => {
      resizeCanvas();
      drawOverlay();
    };
    setStatus(`SNAPSHOT ${snapshot.snapshot_id}`, "ok");
  }

  function resizeCanvas() {
    if (!state.dom || !ui.pageImage.clientWidth || !ui.pageImage.clientHeight) return;
    const ratio = window.devicePixelRatio || 1;
    ui.canvas.width = Math.max(1, Math.round(ui.pageImage.clientWidth * ratio));
    ui.canvas.height = Math.max(1, Math.round(ui.pageImage.clientHeight * ratio));
    ui.canvas.style.width = `${ui.pageImage.clientWidth}px`;
    ui.canvas.style.height = `${ui.pageImage.clientHeight}px`;
    const context = ui.canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function pageDimensions() {
    const page = state.dom?.page || {};
    return {
      width: Number(page.document_width || ui.pageImage.naturalWidth || 1),
      height: Number(page.document_height || ui.pageImage.naturalHeight || 1),
    };
  }

  function canvasRect(element) {
    const page = pageDimensions();
    const width = ui.pageImage.clientWidth || 1;
    const height = ui.pageImage.clientHeight || 1;
    return {
      x: (Number(element.rect?.x || 0) / page.width) * width,
      y: (Number(element.rect?.y || 0) / page.height) * height,
      width: (Number(element.rect?.width || 0) / page.width) * width,
      height: (Number(element.rect?.height || 0) / page.height) * height,
    };
  }

  function drawElement(context, element, color, lineWidth = 2, fill = null) {
    if (!element) return;
    const rect = canvasRect(element);
    context.save();
    context.strokeStyle = color;
    context.lineWidth = lineWidth;
    if (fill) {
      context.fillStyle = fill;
      context.fillRect(rect.x, rect.y, rect.width, rect.height);
    }
    context.strokeRect(rect.x, rect.y, rect.width, rect.height);
    context.restore();
  }

  function drawOverlay() {
    const context = ui.canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, ui.canvas.clientWidth, ui.canvas.clientHeight);
    if (!state.dom) return;

    if (ui.showAllElements.checked) {
      for (const element of state.elements) {
        const rect = canvasRect(element);
        if (rect.width < 3 || rect.height < 3) continue;
        context.strokeStyle = "rgba(140, 236, 255, 0.12)";
        context.lineWidth = 1;
        context.strokeRect(rect.x, rect.y, rect.width, rect.height);
      }
    }

    for (const id of state.cardExampleIds) {
      drawElement(context, state.elementsById.get(id), "#8cff9b", 3, "rgba(140, 255, 155, 0.08)");
    }
    if (state.selectedId) {
      drawElement(context, state.elementsById.get(state.selectedId), "#ffe08a", 3, "rgba(255, 224, 138, 0.08)");
    }
    if (state.hoverId && state.hoverId !== state.selectedId) {
      drawElement(context, state.elementsById.get(state.hoverId), "#8cecff", 2, "rgba(140, 236, 255, 0.05)");
    }
    if (state.dragging && state.dragStart && state.dragCurrent) {
      const x = Math.min(state.dragStart.x, state.dragCurrent.x);
      const y = Math.min(state.dragStart.y, state.dragCurrent.y);
      const width = Math.abs(state.dragCurrent.x - state.dragStart.x);
      const height = Math.abs(state.dragCurrent.y - state.dragStart.y);
      context.save();
      context.strokeStyle = "#98b8ff";
      context.fillStyle = "rgba(152, 184, 255, 0.08)";
      context.lineWidth = 2;
      context.fillRect(x, y, width, height);
      context.strokeRect(x, y, width, height);
      context.restore();
    }
  }

  function eventCanvasPoint(event) {
    const rect = ui.canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

  function canvasToDocument(point) {
    const page = pageDimensions();
    return {
      x: (point.x / Math.max(1, ui.canvas.clientWidth)) * page.width,
      y: (point.y / Math.max(1, ui.canvas.clientHeight)) * page.height,
    };
  }

  function elementAtDocumentPoint(point, minimumWidth = 0, minimumHeight = 0) {
    const candidates = state.elements.filter((element) => {
      const rect = element.rect || {};
      const x = Number(rect.x || 0);
      const y = Number(rect.y || 0);
      const width = Number(rect.width || 0);
      const height = Number(rect.height || 0);
      return (
        width >= minimumWidth &&
        height >= minimumHeight &&
        point.x >= x &&
        point.x <= x + width &&
        point.y >= y &&
        point.y <= y + height
      );
    });
    candidates.sort((a, b) => {
      const areaA = Number(a.rect?.width || 0) * Number(a.rect?.height || 0);
      const areaB = Number(b.rect?.width || 0) * Number(b.rect?.height || 0);
      return areaA - areaB;
    });
    return candidates[0] || null;
  }

  function selectFromPointer(start, end) {
    const deltaX = Math.abs(end.x - start.x);
    const deltaY = Math.abs(end.y - start.y);
    const centerCanvas = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
    const centerDocument = canvasToDocument(centerCanvas);
    if (deltaX < 5 && deltaY < 5) {
      return elementAtDocumentPoint(centerDocument);
    }
    const page = pageDimensions();
    const minimumWidth = (deltaX / Math.max(1, ui.canvas.clientWidth)) * page.width * 0.65;
    const minimumHeight = (deltaY / Math.max(1, ui.canvas.clientHeight)) * page.height * 0.65;
    return elementAtDocumentPoint(centerDocument, minimumWidth, minimumHeight)
      || elementAtDocumentPoint(centerDocument);
  }

  function updateInspector(element) {
    if (!element) {
      ui.inspectId.textContent = "—";
      ui.inspectTag.textContent = "—";
      ui.inspectSelector.textContent = "—";
      ui.inspectValue.textContent = "—";
      ui.inspectRect.textContent = "—";
      return;
    }
    ui.inspectId.textContent = element.id || "—";
    ui.inspectTag.textContent = element.tag || "—";
    ui.inspectSelector.textContent = element.selector || "—";
    ui.inspectValue.textContent = element.href || element.src || element.text || "—";
    const rect = element.rect || {};
    ui.inspectRect.textContent = `${Math.round(rect.x || 0)}, ${Math.round(rect.y || 0)} · ${Math.round(rect.width || 0)} × ${Math.round(rect.height || 0)}`;
  }

  function elementClasses(element) {
    return String(element?.attributes?.class || "")
      .split(/\s+/)
      .map((value) => value.trim())
      .filter((value) => /^[a-zA-Z_][a-zA-Z0-9_-]{0,60}$/.test(value))
      .filter((value) => !/^(active|selected|open|hover|focus|loaded|visible|hidden)$/i.test(value));
  }

  function selectorTail(selector) {
    return String(selector || "").split(/\s*>\s*/).pop().trim();
  }

  function generalizedSingleSelector(element) {
    if (!element) return "";
    const classes = elementClasses(element).slice(0, 3);
    if (classes.length) return `${element.tag}.${classes.join(".")}`;
    return selectorTail(element.selector).replace(/:nth-of-type\(\d+\)/g, "");
  }

  function inferCardSelector(first, second) {
    if (!first || !second) return "";
    const firstClasses = elementClasses(first);
    const secondClasses = new Set(elementClasses(second));
    const commonClasses = firstClasses.filter((name) => secondClasses.has(name));
    if (first.tag === second.tag && commonClasses.length) {
      return `${first.tag}.${commonClasses.slice(0, 3).join(".")}`;
    }
    const normalizedFirst = String(first.selector || "").replace(/:nth-of-type\(\d+\)/g, "");
    const normalizedSecond = String(second.selector || "").replace(/:nth-of-type\(\d+\)/g, "");
    if (normalizedFirst === normalizedSecond) return normalizedFirst;
    if (first.tag === second.tag) return first.tag;
    return "";
  }

  function selectorApproxMatches(element, selector) {
    const value = String(selector || "").trim();
    if (!value) return false;
    const normalizedElement = String(element.selector || "").replace(/:nth-of-type\(\d+\)/g, "");
    const normalizedSelector = value.replace(/:nth-of-type\(\d+\)/g, "");
    if (normalizedElement === normalizedSelector) return true;
    const tail = selectorTail(value);
    const tagMatch = tail.match(/^[a-zA-Z][a-zA-Z0-9-]*/);
    const tag = tagMatch ? tagMatch[0].toLowerCase() : "";
    const classes = Array.from(tail.matchAll(/\.([a-zA-Z_][a-zA-Z0-9_-]*)/g)).map((match) => match[1]);
    if (tag && element.tag !== tag) return false;
    const actualClasses = new Set(elementClasses(element));
    return classes.every((name) => actualClasses.has(name));
  }

  function updateCardMatchCount() {
    const selector = ui.cardSelector.value.trim();
    const count = selector
      ? state.elements.filter((element) => selectorApproxMatches(element, selector)).length
      : 0;
    ui.cardMatchCount.textContent = String(count);
  }

  function updateCardExamples() {
    ui.cardExampleCount.textContent = `${state.cardExampleIds.length} / 2`;
    if (state.cardExampleIds.length >= 2) {
      const selector = inferCardSelector(
        state.elementsById.get(state.cardExampleIds[0]),
        state.elementsById.get(state.cardExampleIds[1]),
      );
      if (selector) ui.cardSelector.value = selector;
    }
    updateCardMatchCount();
    drawOverlay();
  }

  function isDescendantOf(elementId, ancestorId) {
    let current = state.elementsById.get(elementId);
    const visited = new Set();
    while (current && !visited.has(current.id)) {
      if (current.id === ancestorId) return true;
      visited.add(current.id);
      current = state.elementsById.get(current.parent_id);
    }
    return false;
  }

  function relativeSelector(element, card) {
    if (!element || !card || !isDescendantOf(element.id, card.id) || element.id === card.id) {
      return "";
    }
    const parts = [];
    let current = element;
    const visited = new Set();
    while (current && current.id !== card.id && !visited.has(current.id)) {
      visited.add(current.id);
      parts.unshift(selectorTail(current.selector));
      current = state.elementsById.get(current.parent_id);
    }
    return current?.id === card.id ? parts.join(" > ") : "";
  }

  function evidenceValue(target, element) {
    if (target === "url") return element.href || element.attributes?.href || "";
    if (target === "image") return element.src || element.attributes?.src || "";
    return element.text || "";
  }

  function setFieldFromElement(target, element) {
    const card = state.elementsById.get(state.cardExampleIds[0]);
    if (!card) {
      setStatus("SELECT TWO CARD EXAMPLES FIRST", "warn");
      return;
    }
    const selector = relativeSelector(element, card);
    if (!selector) {
      setStatus("FIELD MUST BE INSIDE THE FIRST CARD EXAMPLE", "warn");
      return;
    }
    const value = evidenceValue(target, element);
    if (!value) {
      setStatus(`${target.toUpperCase()} ELEMENT HAS NO USABLE VALUE`, "warn");
      return;
    }
    fieldInput(target).value = selector;
    state.fieldEvidence[target] = {
      target,
      element_id: element.id,
      page_role: "listing",
      selector,
      absolute_selector: element.selector,
      raw_value: value,
      attribute: target === "url" ? "href" : target === "image" ? "src" : null,
    };
    ui.fieldEvidence.textContent = JSON.stringify(state.fieldEvidence[target], null, 2);
    setStatus(`${target.toUpperCase()} MAPPED`, "ok");
  }

  function addExcludeSelector(element) {
    const selector = generalizedSingleSelector(element);
    if (!selector) return;
    const current = ui.excludeSelectors.value
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean);
    if (!current.includes(selector)) current.push(selector);
    ui.excludeSelectors.value = current.join("\n");
    setStatus("EXCLUSION ADDED", "ok");
  }

  function assignElement(element) {
    if (!element) return;
    state.selectedId = element.id;
    updateInspector(element);
    if (state.activeTarget === "card") {
      if (state.cardExampleIds.includes(element.id)) {
        state.cardExampleIds = state.cardExampleIds.filter((id) => id !== element.id);
      } else if (state.cardExampleIds.length < 2) {
        state.cardExampleIds.push(element.id);
      } else {
        state.cardExampleIds[1] = element.id;
      }
      updateCardExamples();
      setStatus(state.cardExampleIds.length < 2 ? "SELECT ONE MORE CARD" : "CARD SELECTOR INFERRED", state.cardExampleIds.length < 2 ? "warn" : "ok");
      return;
    }
    if (state.activeTarget === "exclude") {
      addExcludeSelector(element);
      drawOverlay();
      return;
    }
    setFieldFromElement(state.activeTarget, element);
    drawOverlay();
  }

  function emptyDraft() {
    return {
      schema_version: 1,
      source_id: state.sourceId,
      listing_url: state.listingUrl,
      version: 0,
      status: "draft",
      fields: {},
      detail_page: { enabled: false, fields: {} },
      validation: {
        require_public_detail_url: true,
        require_current_or_future_date: true,
      },
    };
  }

  function applyRuleToEditor(rule) {
    const active = rule || emptyDraft();
    ui.cardSelector.value = active.card?.selector || "";
    ui.excludeSelectors.value = (active.card?.exclude_selectors || []).join("\n");
    for (const name of FIELD_NAMES) {
      fieldInput(name).value = active.fields?.[name]?.selector || "";
    }
    ui.allowSourceDefault.checked = Boolean(active.fields?.where?.allow_source_default);
    ui.detailEnabled.checked = Boolean(active.detail_page?.enabled);
    for (const name of DETAIL_FIELD_NAMES) {
      detailFieldInput(name).value = active.detail_page?.fields?.[name]?.selector || "";
    }
    state.fieldEvidence = {};
    ui.fieldEvidence.textContent = "No field selected.";
    updateCardMatchCount();
    if (rule?.status === "draft") {
      setRuleState("DRAFT", "warn");
    } else if (rule?.status === "published") {
      setRuleState(`PUBLISHED V${rule.version}`, "ok");
    } else {
      setRuleState("NO RULE");
    }
  }

  function renderHistory(history, published) {
    ui.historySelect.innerHTML = "";
    if (!history.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No published versions";
      ui.historySelect.appendChild(option);
      ui.rollbackButton.disabled = true;
      return;
    }
    ui.rollbackButton.disabled = false;
    for (const rule of [...history].reverse()) {
      const option = document.createElement("option");
      option.value = String(rule.version);
      option.textContent = `v${rule.version}${published?.version === rule.version ? " · active" : ""}${rule.based_on_version ? ` · from v${rule.based_on_version}` : ""}`;
      ui.historySelect.appendChild(option);
    }
  }

  function selectorRule(name, selector, { detail = false } = {}) {
    const clean = selector.trim();
    if (!clean) return null;
    const rule = { selector: clean };
    if (!detail && name === "url") rule.attribute = "href";
    if (name === "image") rule.attribute = "src";
    if (name === "summary" || name === "image") rule.optional = true;
    if (name === "where") rule.allow_source_default = detail ? false : ui.allowSourceDefault.checked;
    return rule;
  }

  function buildDraftPayload() {
    const payload = emptyDraft();
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
      const rule = selectorRule(name, fieldInput(name).value);
      if (rule) payload.fields[name] = rule;
    }
    payload.detail_page.enabled = ui.detailEnabled.checked;
    if (payload.detail_page.enabled) {
      for (const name of DETAIL_FIELD_NAMES) {
        const rule = selectorRule(name, detailFieldInput(name).value, { detail: true });
        if (rule) payload.detail_page.fields[name] = rule;
      }
    }
    return payload;
  }

  async function saveDraft({ quiet = false } = {}) {
    if (!state.sourceId || !state.listingUrl) throw new Error("No source/listing selected");
    const payload = buildDraftPayload();
    const saved = await api("/api/local-events/studio/draft", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.loadedRuleState = state.loadedRuleState || {};
    state.loadedRuleState.draft = saved.rule;
    setRuleState("DRAFT", "warn");
    if (!quiet) setStatus("DRAFT SAVED", "ok");
    return saved.rule;
  }

  async function publishRule() {
    setStatus("VALIDATING DRAFT");
    await saveDraft({ quiet: true });
    const payload = await api("/api/local-events/studio/publish", {
      method: "POST",
      body: JSON.stringify({ source_id: state.sourceId, listing_url: state.listingUrl }),
    });
    setStatus(`PUBLISHED V${payload.rule.version}`, "ok");
    await loadContext({ preserveSnapshot: true });
  }

  async function rollbackRule() {
    const version = Number(ui.historySelect.value || 0);
    if (!version) return;
    if (!window.confirm(`Republish version ${version} as a new active version?`)) return;
    const payload = await api("/api/local-events/studio/rollback", {
      method: "POST",
      body: JSON.stringify({
        source_id: state.sourceId,
        listing_url: state.listingUrl,
        version,
      }),
    });
    setStatus(`ROLLED BACK AS V${payload.rule.version}`, "ok");
    await loadContext({ preserveSnapshot: true });
  }

  async function exportRule() {
    const params = query({ source_id: state.sourceId, listing_url: state.listingUrl });
    const payload = await api(`/api/local-events/studio/export?${params}`);
    const blob = new Blob([`${JSON.stringify(payload.rule, null, 2)}\n`], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${state.sourceId}-local-event-rule-v${payload.rule.version || "draft"}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus("RULE EXPORTED", "ok");
  }

  async function importRule(file) {
    const text = await file.text();
    const rule = JSON.parse(text);
    await api("/api/local-events/studio/import", {
      method: "POST",
      body: JSON.stringify({ rule }),
    });
    setStatus("RULE IMPORTED AS DRAFT", "ok");
    await loadContext({ preserveSnapshot: true });
  }

  async function captureSnapshot() {
    ui.captureButton.disabled = true;
    setStatus("CAPTURING OFFICIAL LIST");
    try {
      const payload = await api("/api/local-events/studio/capture", {
        method: "POST",
        body: JSON.stringify({ source_id: state.sourceId, listing_url: state.listingUrl }),
      });
      setStatus("CAPTURE COMPLETE", "ok");
      await loadContext();
      ui.snapshotSelect.value = payload.snapshot.snapshot_id;
      await loadSnapshot(payload.snapshot.snapshot_id);
    } finally {
      ui.captureButton.disabled = false;
    }
  }

  function setActiveTarget(target) {
    state.activeTarget = target;
    document.querySelectorAll(".mode-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.target === target);
    });
    setStatus(`TARGET: ${target.toUpperCase()}`);
  }

  function bindEvents() {
    ui.sourceSelect.addEventListener("change", async () => {
      state.sourceId = ui.sourceSelect.value;
      populateListingSelect();
      await guarded(() => loadContext());
    });
    ui.listingSelect.addEventListener("change", async () => {
      state.listingUrl = ui.listingSelect.value;
      await guarded(() => loadContext());
    });
    ui.snapshotSelect.addEventListener("change", () => guarded(() => loadSnapshot(ui.snapshotSelect.value)));
    ui.captureButton.addEventListener("click", () => guarded(captureSnapshot));
    ui.reloadButton.addEventListener("click", () => guarded(() => loadContext({ preserveSnapshot: true })));
    ui.showAllElements.addEventListener("change", drawOverlay);
    ui.clearCardExamples.addEventListener("click", () => {
      state.cardExampleIds = [];
      updateCardExamples();
      setStatus("CARD EXAMPLES CLEARED");
    });
    ui.cardSelector.addEventListener("input", updateCardMatchCount);
    ui.saveDraftButton.addEventListener("click", () => guarded(() => saveDraft()));
    ui.publishButton.addEventListener("click", () => guarded(publishRule));
    ui.rollbackButton.addEventListener("click", () => guarded(rollbackRule));
    ui.exportButton.addEventListener("click", () => guarded(exportRule));
    ui.importInput.addEventListener("change", () => {
      const file = ui.importInput.files?.[0];
      if (file) guarded(() => importRule(file));
      ui.importInput.value = "";
    });
    document.querySelectorAll(".mode-button").forEach((button) => {
      button.addEventListener("click", () => setActiveTarget(button.dataset.target));
    });
    ui.fieldEditor.addEventListener("click", (event) => {
      const button = event.target.closest("[data-clear-field]");
      if (!button) return;
      const name = button.dataset.clearField;
      fieldInput(name).value = "";
      delete state.fieldEvidence[name];
      ui.fieldEvidence.textContent = "No field selected.";
    });
    ui.detailFields.addEventListener("click", (event) => {
      const button = event.target.closest("[data-clear-detail-field]");
      if (!button) return;
      detailFieldInput(button.dataset.clearDetailField).value = "";
    });

    ui.canvas.addEventListener("pointerdown", (event) => {
      if (!state.dom) return;
      ui.canvas.setPointerCapture(event.pointerId);
      state.dragging = true;
      state.dragStart = eventCanvasPoint(event);
      state.dragCurrent = state.dragStart;
      drawOverlay();
    });
    ui.canvas.addEventListener("pointermove", (event) => {
      if (!state.dom) return;
      const point = eventCanvasPoint(event);
      if (state.dragging) {
        state.dragCurrent = point;
        drawOverlay();
        return;
      }
      const element = elementAtDocumentPoint(canvasToDocument(point));
      const nextId = element?.id || null;
      if (nextId !== state.hoverId) {
        state.hoverId = nextId;
        updateInspector(element);
        drawOverlay();
      }
    });
    ui.canvas.addEventListener("pointerup", (event) => {
      if (!state.dragging) return;
      state.dragCurrent = eventCanvasPoint(event);
      const element = selectFromPointer(state.dragStart, state.dragCurrent);
      state.dragging = false;
      state.dragStart = null;
      state.dragCurrent = null;
      assignElement(element);
    });
    ui.canvas.addEventListener("pointercancel", () => {
      state.dragging = false;
      state.dragStart = null;
      state.dragCurrent = null;
      drawOverlay();
    });
    window.addEventListener("resize", () => {
      resizeCanvas();
      drawOverlay();
    });
  }

  async function guarded(operation) {
    try {
      await operation();
    } catch (error) {
      setStatus(error.message || String(error), "error");
    }
  }

  document.addEventListener("DOMContentLoaded", initialize);
})();
