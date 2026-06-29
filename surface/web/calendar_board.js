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

  var cardStyle = "height:100%;max-height:100%;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;padding:20px 26px 18px;border-left:5px solid #ffe58a;background:#101313;";
  var labelStyle = "flex:0 0 auto;color:#8f9998;font-size:12px;line-height:1;letter-spacing:.24em;font-weight:800;margin:0 0 8px;text-transform:uppercase;";
  var metaStyle = "flex:0 0 auto;display:flex;align-items:baseline;gap:10px;min-height:22px;max-height:22px;overflow:hidden;margin:3px 0;white-space:nowrap;";
  var metaKeyStyle = "flex:0 0 68px;color:#8f9998;font-size:13px;line-height:1;letter-spacing:.2em;font-weight:800;text-transform:uppercase;";
  var metaValueStyle = "min-width:0;flex:1;color:#85e8f4;font-size:16px;line-height:1.15;letter-spacing:.045em;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
  var summaryStyle = "flex:1 1 auto;min-height:0;max-height:82px;overflow:hidden;color:#c9cdca;font-size:15px;line-height:1.34;letter-spacing:.015em;font-weight:700;margin:9px 0 8px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;";
  var actionsStyle = "flex:0 0 auto;margin-top:auto;padding-top:8px;";
  var linkStyle = "display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;min-height:42px;padding:12px 18px;border:1px solid #4b5454;color:#ffe58a;text-decoration:none;font-size:14px;line-height:1;letter-spacing:.08em;font-weight:900;";

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
  function shorten(value, n) {
    var text = clean(value);
    return text.length <= n ? text : text.slice(0, n - 1).trimEnd() + "…";
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
    return {
      title: clean(raw.title || raw.name || raw.summary || ""),
      when: clean(raw.when || raw.date || raw.date_text || raw.when_text || raw.start_date || raw.start || ""),
      where: clean(raw.where || raw.venue || raw.location || raw.place || ""),
      source: clean(raw.source_name || raw.host || raw.source || raw.organizer || "Official source"),
      summary: clean(raw.summary || raw.description || raw.why_text || ""),
      url: /^https?:\/\//i.test(url) ? url : ""
    };
  }
  function titleStyle(title) {
    var n = clean(title).length;
    var size = n > 86 ? 18 : n > 64 ? 20 : n > 42 ? 22 : 24;
    return "flex:0 0 auto;color:#ffe58a;font-size:" + size + "px;line-height:1.12;letter-spacing:.055em;font-weight:900;max-height:" + Math.ceil(size * 2.3) + "px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:anywhere;margin:0 0 8px;";
  }
  function installPagerStyle() {
    if (document.getElementById("local-event-isolated-style")) return;
    var style = document.createElement("style");
    style.id = "local-event-isolated-style";
    style.textContent = [
      "#localEventList{height:100%!important;min-height:0!important;overflow:hidden!important;}",
      "#localEventPrevButton,#localEventNextButton{position:relative!important;z-index:50!important;min-width:44px!important;min-height:36px!important;cursor:pointer!important;touch-action:manipulation!important;pointer-events:auto!important;}"
    ].join("\n");
    document.head.appendChild(style);
  }
  function meta(label, value, maxLen) {
    value = clean(value);
    if (!value) return "";
    return '<div class="infoscreen-event-meta" style="' + metaStyle + '"><span style="' + metaKeyStyle + '">' + esc(label) + '</span><b style="' + metaValueStyle + '">' + esc(shorten(value, maxLen || 90)) + '</b></div>';
  }
  function renderEmpty(text) {
    var list = byId("localEventList");
    var counter = byId("localEventCounter");
    var prev = byId("localEventPrevButton");
    var next = byId("localEventNextButton");
    installPagerStyle();
    if (list) list.innerHTML = '<div style="' + cardStyle + '"><div style="' + labelStyle + '">EVENT</div><div style="color:#ffe58a;font-size:20px;font-weight:900;letter-spacing:.06em;">' + esc(text) + '</div></div>';
    if (counter) counter.textContent = "";
    if (prev) prev.disabled = true;
    if (next) next.disabled = true;
  }
  function render() {
    var list = byId("localEventList");
    var counter = byId("localEventCounter");
    var prev = byId("localEventPrevButton");
    var next = byId("localEventNextButton");
    if (!list) return;
    installPagerStyle();
    if (!items.length) {
      var rawCount = lastPayload && typeof lastPayload.count !== "undefined" ? lastPayload.count : rows(lastPayload).length;
      renderEmpty("NO RENDERABLE EVENTS · RAW " + rawCount);
      return;
    }
    if (page < 0) page = items.length - 1;
    if (page >= items.length) page = 0;
    var item = items[page];
    var title = item.title || "Local event";
    list.innerHTML = [
      '<article class="infoscreen-event-card" style="' + cardStyle + '">',
      '<div class="infoscreen-event-label" style="' + labelStyle + '">EVENT</div>',
      '<div class="infoscreen-event-title" style="' + titleStyle(title) + '">', esc(shorten(title, 92)), '</div>',
      meta('WHEN', item.when, 72),
      meta('WHERE', item.where, 72),
      meta('HOST', item.source, 58),
      item.summary ? '<div class="infoscreen-event-summary" style="' + summaryStyle + '">' + esc(shorten(item.summary, 220)) + '</div>' : '<div style="flex:1 1 auto;min-height:0;"></div>',
      '<div class="infoscreen-event-actions" style="' + actionsStyle + '">',
      item.url ? '<a class="infoscreen-event-link" style="' + linkStyle + '" href="' + esc(item.url) + '" target="_blank" rel="noopener noreferrer">OPEN OFFICIAL LINK</a>' : '<span style="color:#8f9998;font-size:13px;font-weight:800;letter-spacing:.08em;">NO LINK IN SOURCE</span>',
      '</div></article>'
    ].join("");
    if (counter) counter.textContent = (page + 1) + "/" + items.length;
    if (prev) prev.disabled = items.length <= 1;
    if (next) next.disabled = items.length <= 1;
  }
  function apply(payload) {
    lastPayload = payload || {};
    items = rows(payload).map(normalize).filter(function (item) {
      return item.title && item.url;
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
    if (!items.length || items.length <= 1) return;
    page += delta;
    render();
  }
  function bind() {
    var openButton = byId("localEventLocationButton");
    var cancelButton = byId("localEventCancelButton");
    var searchButton = byId("localEventSearchButton");
    var prevButton = byId("localEventPrevButton");
    var nextButton = byId("localEventNextButton");
    var modal = byId("localEventModal");
    var input = byId("localEventLocationInput");
    if (openButton) openButton.addEventListener("click", function (e) {
      e.preventDefault();
      if (modal) modal.hidden = false;
      if (input) {
        input.value = clean(input.value) || "Punggol Singapore";
        setTimeout(function () { input.focus(); input.select(); }, 20);
      }
    });
    if (cancelButton) cancelButton.addEventListener("click", function (e) {
      e.preventDefault();
      if (modal) modal.hidden = true;
    });
    if (searchButton) searchButton.addEventListener("click", searchLocalEvents);
    if (input) input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") searchLocalEvents(e);
      if (e.key === "Escape" && modal) modal.hidden = true;
    });
    if (prevButton) prevButton.addEventListener("click", function (e) { e.preventDefault(); movePage(-1); });
    if (nextButton) nextButton.addEventListener("click", function (e) { e.preventDefault(); movePage(1); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") movePage(-1);
      if (e.key === "ArrowRight") movePage(1);
    });
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
