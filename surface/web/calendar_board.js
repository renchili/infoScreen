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
