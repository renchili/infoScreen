(function () {
  var CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  var items = [];
  var offset = 0;
  var timer = null;
  var empty = true;
  var spinHandles = [];

  function clearSpin() {
    spinHandles.forEach(function (h) {
      if (h.type === "timeout") clearTimeout(h.id);
      if (h.type === "interval") clearInterval(h.id);
    });
    spinHandles = [];
  }

  function later(fn, ms) {
    var id = setTimeout(fn, ms);
    spinHandles.push({ type: "timeout", id: id });
    return id;
  }

  function tick(fn, ms) {
    var id = setInterval(fn, ms);
    spinHandles.push({ type: "interval", id: id });
    return id;
  }

  function esc(v) {
    return String(v || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalizeText(v) {
    return String(v || "NO SCHEDULE EVENTS").replace(/\s+/g, " ").trim().toUpperCase();
  }

  function ensure() {
    var box = document.getElementById("agendaList");
    if (!box) return null;
    box.className = "inner agenda calendar-board" + (empty ? " empty-schedule" : "");
    if (!document.getElementById("calendarBoardRows")) {
      box.innerHTML = '<div class="calendar-board-head"><span>TIME</span><span>EVENT</span></div><div class="calendar-board-rows" id="calendarBoardRows"></div>';
    }
    return document.getElementById("calendarBoardRows");
  }

  function capacity() {
    if (empty) return 1;
    var rows = document.getElementById("calendarBoardRows");
    var h = rows ? rows.clientHeight : 40;
    return Math.max(1, Math.min(6, Math.floor((h - 2) / 32)));
  }

  function slotCount() {
    var rows = document.getElementById("calendarBoardRows");
    var w = rows ? rows.clientWidth : 260;
    return Math.max(18, Math.min(42, Math.floor((w - 104) / 14)));
  }

  function cells(text) {
    var raw = normalizeText(text);
    var n = slotCount();
    if (raw.length > n) raw = raw.slice(0, n);
    var html = "";
    for (var i = 0; i < raw.length; i++) {
      var ch = raw[i];
      html += ch === " "
        ? '<span class="calendar-board-cell blank">&nbsp;</span>'
        : '<span class="calendar-board-cell" data-final="' + esc(ch) + '">' + esc(ch) + '</span>';
    }
    return html;
  }

  function rowHtml(item) {
    return '<div class="calendar-board-row"><div class="calendar-board-time">' + cells(item.time || "") + '</div><div class="calendar-board-event">' + cells(item.title || item.text || "NO SCHEDULE EVENTS") + '</div></div>';
  }

  function animateBoard(rows) {
    var cellsList = Array.prototype.slice.call(rows.querySelectorAll(".calendar-board-cell:not(.blank)"));
    cellsList.forEach(function (cell, idx) {
      var finalChar = cell.getAttribute("data-final") || cell.textContent || "";
      later(function () {
        var step = 0;
        cell.classList.add("flipping");
        var id = tick(function () {
          if (step < CHARSET.length) {
            cell.textContent = CHARSET[step++];
            return;
          }
          clearInterval(id);
          cell.textContent = finalChar;
          cell.classList.remove("flipping");
          cell.classList.add("settled");
          later(function () { cell.classList.remove("settled"); }, 140);
        }, 26);
      }, idx * 95);
    });
  }

  function render(animate) {
    var rows = ensure();
    if (!rows) return;
    clearSpin();
    var list = empty ? [{ time: "", title: "NO SCHEDULE EVENTS" }] : items;
    var n = Math.min(capacity(), list.length);
    var html = "";
    for (var i = 0; i < n; i++) html += rowHtml(list[(offset + i) % list.length]);
    rows.innerHTML = html;
    if (animate !== false) requestAnimationFrame(function () { animateBoard(rows); });
  }

  function rotate() {
    if (!empty) {
      var n = Math.min(capacity(), items.length || 1);
      if (items.length > n) offset = (offset + n) % items.length;
    }
    render(true);
  }

  async function load() {
    try {
      var res = await fetch("schedule.json?_=" + Date.now(), { cache: "no-store" });
      var data = await res.json();
      var events = Array.isArray(data) ? data : (data.events || []);
      items = events.map(function (e) {
        return { time: e.time || e.start || e.start_time || e.date || "", title: e.text || e.title || e.summary || "Untitled" };
      });
      empty = items.length === 0;
      offset = 0;
      render(true);
      if (timer) clearInterval(timer);
      timer = setInterval(rotate, 7000);
    } catch (err) {
      items = [{ time: "", title: "SCHEDULE ERROR" }];
      empty = true;
      render(true);
    }
  }

  window.__calendarBoardLoad = load;
  window.loadAgenda = load;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
  else load();
  if (window.ResizeObserver) {
    var box = document.getElementById("agendaList");
    if (box) new ResizeObserver(function () { render(false); }).observe(box);
  }
})();

(function () {
  var API = "/api/local-events/search";
  var page = 0;
  var items = [];
  var lastPayload = null;

  function byId(id) { return document.getElementById(id); }
  function clean(value) { return String(value == null ? "" : value).replace(/\s+/g, " ").trim(); }
  function esc(value) {
    return clean(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function rows(payload) {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    if (Array.isArray(payload.results)) return payload.results;
    if (Array.isArray(payload.events)) return payload.events;
    if (Array.isArray(payload.items)) return payload.items;
    return [];
  }

  function normalize(raw) {
    raw = raw || {};
    var url = clean(raw.url || raw.link || raw.href || "");
    var source = clean(raw.source_name || raw.host || raw.source || raw.organizer || "Official source");
    var title = clean(raw.title || raw.name || raw.summary || "");
    var when = clean(raw.when || raw.date || raw.date_text || raw.when_text || raw.start_date || raw.start || "");
    var where = clean(raw.where || raw.venue || raw.location || raw.place || "");
    var summary = clean(raw.summary || raw.description || raw.why_text || raw.subtitle || "");
    return {
      title: title,
      when: when,
      where: where,
      source: source,
      summary: summary,
      url: /^https?:\/\//i.test(url) ? url : ""
    };
  }

  function installReadableStyle() {
    if (document.getElementById("local-event-readable-style")) return;
    var style = document.createElement("style");
    style.id = "local-event-readable-style";
    style.textContent = [
      "#localEventBox .inner{position:relative!important;height:100%!important;min-height:0!important;overflow:hidden!important;padding:7px 10px 9px 10px!important;display:block!important;background:#050606!important;}",
      "#localEventBox .local-event-toolbar{position:absolute!important;top:6px!important;right:8px!important;height:23px!important;display:flex!important;align-items:center!important;gap:6px!important;z-index:5!important;margin:0!important;padding:0!important;background:rgba(5,6,6,.88)!important;border-radius:999px!important;}",
      "#localEventBox #localEventCounter{min-width:48px!important;text-align:right!important;color:#7d8782!important;font-size:12px!important;line-height:21px!important;font-weight:900!important;letter-spacing:.04em!important;}",
      "#localEventBox #localEventPrevButton,#localEventBox #localEventNextButton,#localEventBox #localEventLocationButton{appearance:none!important;-webkit-appearance:none!important;box-sizing:border-box!important;display:inline-grid!important;place-items:center!important;width:23px!important;height:23px!important;min-width:23px!important;min-height:23px!important;margin:0!important;padding:0!important;border:1px solid #3a3f3d!important;border-radius:999px!important;background:#050606!important;color:#8cecff!important;font-size:14px!important;font-weight:950!important;line-height:1!important;}",
      "#localEventBox #localEventPrevButton:disabled,#localEventBox #localEventNextButton:disabled{opacity:.28!important;}",
      "#localEventList{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0!important;padding:0!important;display:block!important;background:transparent!important;}",
      "#localEventList .infoscreen-event-card{height:100%!important;box-sizing:border-box!important;display:grid!important;grid-template-rows:auto auto auto auto minmax(0,1fr) auto!important;gap:5px!important;overflow:hidden!important;padding:9px 10px 9px 12px!important;border-left:3px solid #ffe08a!important;background:rgba(255,224,138,.045)!important;color:#d7ddd9!important;text-decoration:none!important;}",
      "#localEventList .event-source{max-width:calc(100% - 128px)!important;color:#8cecff!important;font-size:11px!important;line-height:1.15!important;font-weight:950!important;letter-spacing:.08em!important;text-transform:uppercase!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;}",
      "#localEventList .event-title{display:block!important;color:#ffe08a!important;font-size:16px!important;line-height:1.12!important;font-weight:950!important;letter-spacing:.01em!important;text-decoration:none!important;overflow:hidden!important;display:-webkit-box!important;-webkit-line-clamp:2!important;-webkit-box-orient:vertical!important;}",
      "#localEventList .event-fact{display:grid!important;grid-template-columns:48px minmax(0,1fr)!important;gap:8px!important;align-items:start!important;min-height:0!important;color:#d7ddd9!important;font-size:12px!important;line-height:1.18!important;font-weight:850!important;overflow:hidden!important;}",
      "#localEventList .event-label{color:#7d8782!important;font-size:10px!important;line-height:1.2!important;font-weight:950!important;letter-spacing:.12em!important;text-transform:uppercase!important;}",
      "#localEventList .event-value{color:#8cecff!important;overflow:hidden!important;display:-webkit-box!important;-webkit-line-clamp:2!important;-webkit-box-orient:vertical!important;}",
      "#localEventList .event-about{min-height:0!important;overflow:hidden!important;color:#d7ddd9!important;font-size:12px!important;line-height:1.2!important;font-weight:760!important;display:-webkit-box!important;-webkit-line-clamp:5!important;-webkit-box-orient:vertical!important;}",
      "#localEventList .event-about .event-label{display:block!important;margin-bottom:2px!important;}",
      "#localEventList .event-link{align-self:end!important;justify-self:start!important;color:#050606!important;background:#ffe08a!important;border:1px solid #ffe08a!important;border-radius:999px!important;padding:4px 10px!important;font-size:10px!important;line-height:1!important;font-weight:950!important;letter-spacing:.08em!important;text-decoration:none!important;text-transform:uppercase!important;}",
      "#localEventList .infoscreen-local-empty{height:100%!important;display:grid!important;place-items:center!important;color:#7d8782!important;font-size:14px!important;font-weight:900!important;letter-spacing:.05em!important;text-transform:uppercase!important;text-align:center!important;}"
    ].join("\n");
    document.head.appendChild(style);
  }

  function renderEmpty(text) {
    var list = byId("localEventList");
    var counter = byId("localEventCounter");
    var prev = byId("localEventPrevButton");
    var next = byId("localEventNextButton");
    installReadableStyle();
    if (list) list.innerHTML = '<div class="infoscreen-local-empty">' + esc(text) + '</div>';
    if (counter) counter.textContent = "";
    if (prev) prev.disabled = true;
    if (next) next.disabled = true;
  }

  function fact(label, value) {
    if (!clean(value)) return "";
    return '<div class="event-fact"><div class="event-label">' + esc(label) + '</div><div class="event-value">' + esc(value) + '</div></div>';
  }

  function cardHtml(item) {
    var title = item.title || "Local event";
    var about = item.summary || "Open the official source for event details.";
    var titleHtml = item.url
      ? '<a class="event-title" href="' + esc(item.url) + '" target="_blank" rel="noopener noreferrer">' + esc(title) + '</a>'
      : '<div class="event-title">' + esc(title) + '</div>';
    var linkHtml = item.url
      ? '<a class="event-link" href="' + esc(item.url) + '" target="_blank" rel="noopener noreferrer">OPEN OFFICIAL SOURCE ↗</a>'
      : '';
    return [
      '<article class="infoscreen-event-card">',
      '<div class="event-source">', esc(item.source || "Official source"), '</div>',
      titleHtml,
      fact("WHEN", item.when || "Date not published"),
      fact("WHERE", item.where || "Venue not published"),
      '<div class="event-about"><span class="event-label">ABOUT</span>', esc(about), '</div>',
      linkHtml,
      '</article>'
    ].join("");
  }

  function render() {
    var list = byId("localEventList");
    var counter = byId("localEventCounter");
    var prev = byId("localEventPrevButton");
    var next = byId("localEventNextButton");
    if (!list) return;
    installReadableStyle();
    if (!items.length) {
      var rawCount = lastPayload && typeof lastPayload.count !== "undefined" ? lastPayload.count : rows(lastPayload).length;
      renderEmpty("NO RENDERABLE EVENTS · RAW " + rawCount);
      return;
    }
    if (page < 0) page = items.length - 1;
    if (page >= items.length) page = 0;
    list.innerHTML = cardHtml(items[page]);
    if (counter) counter.textContent = (page + 1) + "/" + items.length;
    if (prev) prev.disabled = items.length <= 1;
    if (next) next.disabled = items.length <= 1;
  }

  function apply(payload) {
    lastPayload = payload || {};
    items = rows(payload).map(normalize).filter(function (item) {
      return item.title;
    });
    page = 0;
    render();
  }

  async function loadLocalEvents() {
    try {
      var resp = await fetch(API + "?_=" + Date.now(), { cache: "no-store" });
      var payload = await resp.json();
      if (!resp.ok) throw new Error(payload.error || ("HTTP " + resp.status));
      apply(payload);
    } catch (err) {
      renderEmpty("LOCAL EVENTS UNAVAILABLE · " + err.message);
    }
  }

  async function searchLocalEvents(event) {
    if (event) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    var input = byId("localEventLocationInput");
    var err = byId("localEventModalError");
    var button = byId("localEventSearchButton");
    var location = clean(input && input.value) || "Punggol Singapore";
    if (err) err.textContent = "Searching official sources…";
    if (button) button.disabled = true;
    renderEmpty("SEARCHING OFFICIAL SOURCES…");
    try {
      var resp = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ location: location })
      });
      var payload = await resp.json();
      if (!resp.ok) throw new Error(payload.error || payload.stderr || ("HTTP " + resp.status));
      var modal = byId("localEventModal");
      if (modal) modal.hidden = true;
      if (err) err.textContent = "";
      apply(payload);
    } catch (e) {
      if (err) err.textContent = "Search failed: " + e.message;
      renderEmpty("LOCAL EVENT SEARCH FAILED · " + e.message);
    } finally {
      if (button) button.disabled = false;
    }
  }

  function movePage(delta) {
    if (!items.length) return;
    page += delta;
    render();
  }

  function claim(id) {
    var el = byId(id);
    if (!el || !el.parentNode) return el;
    var clone = el.cloneNode(true);
    el.parentNode.replaceChild(clone, el);
    return clone;
  }

  function bind() {
    var openButton = claim("localEventLocationButton");
    var cancelButton = claim("localEventCancelButton");
    var searchButton = claim("localEventSearchButton");
    var prevButton = claim("localEventPrevButton");
    var nextButton = claim("localEventNextButton");
    var input = claim("localEventLocationInput");
    var modal = byId("localEventModal");
    if (openButton) openButton.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (modal) modal.hidden = false;
      if (input) {
        input.value = clean(input.value) || "Punggol Singapore";
        setTimeout(function () { input.focus(); input.select(); }, 20);
      }
    });
    if (cancelButton) cancelButton.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (modal) modal.hidden = true;
    });
    if (searchButton) searchButton.addEventListener("click", searchLocalEvents);
    if (input) input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") searchLocalEvents(e);
      if (e.key === "Escape" && modal) modal.hidden = true;
    });
    if (prevButton) prevButton.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); movePage(-1); });
    if (nextButton) nextButton.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); movePage(1); });
  }

  window.__localEventReload = loadLocalEvents;
  window.__localEventSearch = searchLocalEvents;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bind();
      loadLocalEvents();
    });
  } else {
    bind();
    loadLocalEvents();
  }
})();

(function () {
  function byId(id) { return document.getElementById(id); }
  function clean(value) { return String(value == null ? "" : value).replace(/\s+/g, " ").trim(); }
  function esc(value) {
    return clean(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function installMarketStyle() {
    if (document.getElementById("market-config-style")) return;
    var style = document.createElement("style");
    style.id = "market-config-style";
    style.textContent = [
      ".box[data-title='market'] .market-toolbar{position:absolute;top:6px;right:8px;display:flex;gap:6px;z-index:8;background:rgba(5,6,6,.9);border-radius:999px;}",
      ".box[data-title='market'] .market-config-button{appearance:none;-webkit-appearance:none;width:24px;height:24px;border:1px solid #3a3f3d;border-radius:999px;background:#050606;color:#8cecff;font:950 12px/1 inherit;display:grid;place-items:center;cursor:pointer;padding:0;}",
      ".market-config-modal[hidden]{display:none!important;}",
      ".market-config-modal{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.72);display:grid;place-items:center;}",
      ".market-config-card{width:min(420px,calc(100vw - 28px));background:#090b0c;border:1px solid #3a3f3d;padding:16px;color:#d7ddd9;box-shadow:0 18px 80px rgba(0,0,0,.7);}",
      ".market-config-title{color:#ffe08a;font-size:14px;font-weight:950;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px;}",
      "#marketSymbolInput{width:100%;height:82px;background:#050606;color:#d7ddd9;border:1px solid #3a3f3d;padding:10px;font:900 14px/1.4 inherit;resize:none;outline:none;}",
      ".market-config-hint{color:#7d8782;font-size:11px;line-height:1.35;margin-top:8px;}",
      "#marketConfigError{min-height:18px;color:#ff8c8c;font-size:12px;font-weight:800;margin-top:8px;}",
      ".market-config-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px;}",
      ".market-config-actions button{border:1px solid #3a3f3d;background:#050606;color:#d7ddd9;padding:7px 11px;font:900 12px/1 inherit;cursor:pointer;}",
      ".market-config-actions button:last-child{background:#ffe08a;color:#050606;border-color:#ffe08a;}"
    ].join("\n");
    document.head.appendChild(style);
  }

  function ensureMarketControls() {
    installMarketStyle();
    var box = document.querySelector(".box[data-title='market']");
    if (!box || byId("marketConfigButton")) return;
    var toolbar = document.createElement("div");
    toolbar.className = "market-toolbar";
    toolbar.innerHTML = '<button id="marketConfigButton" class="market-config-button" type="button" title="Configure stocks" aria-label="Configure stocks">⚙</button><button id="marketRefreshButton" class="market-config-button" type="button" title="Refresh market" aria-label="Refresh market">↻</button>';
    box.appendChild(toolbar);

    var modal = document.createElement("div");
    modal.id = "marketConfigModal";
    modal.className = "market-config-modal";
    modal.hidden = true;
    modal.innerHTML = [
      '<div class="market-config-card" role="dialog" aria-modal="true" aria-label="Configure market symbols">',
      '<div class="market-config-title">Market symbols</div>',
      '<textarea id="marketSymbolInput" spellcheck="false" placeholder="AAPL, NVDA, MSFT, TSLA"></textarea>',
      '<div class="market-config-hint">Comma / space / newline separated. Saved to surface/.env/market_config.json.</div>',
      '<div id="marketConfigError"></div>',
      '<div class="market-config-actions"><button id="marketConfigCancelButton" type="button">Cancel</button><button id="marketConfigSaveButton" type="button">Save & Refresh</button></div>',
      '</div>'
    ].join("");
    document.body.appendChild(modal);
  }

  async function loadConfigIntoModal() {
    var input = byId("marketSymbolInput");
    var err = byId("marketConfigError");
    if (err) err.textContent = "";
    try {
      var resp = await fetch("/api/market-config?_=" + Date.now(), { cache: "no-store" });
      var data = await resp.json();
      var symbols = Array.isArray(data.symbols) ? data.symbols : [];
      if (input) input.value = symbols.join(", ");
    } catch (e) {
      if (err) err.textContent = "Cannot load current symbols.";
    }
  }

  function parseSymbols(value) {
    var out = [];
    clean(value).split(/[\s,;]+/).forEach(function (raw) {
      var symbol = raw.trim().toUpperCase();
      if (symbol && out.indexOf(symbol) < 0) out.push(symbol);
    });
    return out.slice(0, 12);
  }

  async function saveAndRefresh() {
    var input = byId("marketSymbolInput");
    var err = byId("marketConfigError");
    var save = byId("marketConfigSaveButton");
    var symbols = parseSymbols(input && input.value);
    if (!symbols.length) {
      if (err) err.textContent = "Enter at least one symbol.";
      return;
    }
    if (save) save.disabled = true;
    if (err) err.textContent = "Saving symbols…";
    try {
      var resp = await fetch("/api/market-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: symbols })
      });
      var data = await resp.json();
      if (!resp.ok || data.ok === false) throw new Error(data.error || ("HTTP " + resp.status));
      if (err) err.textContent = "Refreshing market data…";
      await fetch("/api/market-refresh", { method: "POST" });
      var modal = byId("marketConfigModal");
      if (modal) modal.hidden = true;
      if (window.loadMarket) window.loadMarket();
      if (window.loadTopMarketTape) window.loadTopMarketTape();
    } catch (e) {
      if (err) err.textContent = "Save failed: " + e.message;
    } finally {
      if (save) save.disabled = false;
    }
  }

  async function refreshMarketNow() {
    var button = byId("marketRefreshButton");
    if (button) button.disabled = true;
    try {
      await fetch("/api/market-refresh", { method: "POST" });
      if (window.loadMarket) window.loadMarket();
      if (window.loadTopMarketTape) window.loadTopMarketTape();
    } finally {
      if (button) button.disabled = false;
    }
  }

  function bindMarketControls() {
    ensureMarketControls();
    var config = byId("marketConfigButton");
    var refresh = byId("marketRefreshButton");
    var cancel = byId("marketConfigCancelButton");
    var save = byId("marketConfigSaveButton");
    var modal = byId("marketConfigModal");
    if (config) config.addEventListener("click", function (e) {
      e.preventDefault();
      if (modal) modal.hidden = false;
      loadConfigIntoModal();
      setTimeout(function () { var input = byId("marketSymbolInput"); if (input) input.focus(); }, 20);
    });
    if (refresh) refresh.addEventListener("click", function (e) { e.preventDefault(); refreshMarketNow(); });
    if (cancel) cancel.addEventListener("click", function (e) { e.preventDefault(); if (modal) modal.hidden = true; });
    if (save) save.addEventListener("click", function (e) { e.preventDefault(); saveAndRefresh(); });
    if (modal) modal.addEventListener("click", function (e) { if (e.target === modal) modal.hidden = true; });
  }

  window.__marketConfigOpen = function () {
    ensureMarketControls();
    var modal = byId("marketConfigModal");
    if (modal) modal.hidden = false;
    loadConfigIntoModal();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindMarketControls);
  else bindMarketControls();
})();
