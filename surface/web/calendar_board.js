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
    return String(v || "NO SCHEDULE EVENTS")
      .replace(/\s+/g, " ")
      .trim()
      .toUpperCase();
  }

  function ensure() {
    var box = document.getElementById("agendaList");
    if (!box) return null;
    box.className = "inner agenda calendar-board" + (empty ? " empty-schedule" : "");
    if (!document.getElementById("calendarBoardRows")) {
      box.innerHTML =
        '<div class="calendar-board-head"><span>TIME</span><span>EVENT</span></div>' +
        '<div class="calendar-board-rows" id="calendarBoardRows"></div>';
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
    return '<div class="calendar-board-row">' +
      '<div class="calendar-board-time">' + cells(item.time || "") + '</div>' +
      '<div class="calendar-board-event">' + cells(item.title || item.text || "NO SCHEDULE EVENTS") + '</div>' +
      '</div>';
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
  function renderEmpty(text) {
    var list = byId("localEventList");
    var counter = byId("localEventCounter");
    var prev = byId("localEventPrevButton");
    var next = byId("localEventNextButton");
    if (list) {
      list.dataset.owner = "external-local-events";
      list.innerHTML = '<div class="local-event-empty">' + esc(text) + '</div>';
    }
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
    list.dataset.owner = "external-local-events";
    if (!items.length) {
      var rawCount = lastPayload && typeof lastPayload.count !== "undefined" ? lastPayload.count : rows(lastPayload).length;
      renderEmpty("NO RENDERABLE EVENTS · RAW " + rawCount);
      return;
    }
    if (page < 0) page = items.length - 1;
    if (page >= items.length) page = 0;
    var item = items[page];
    list.innerHTML = [
      '<div class="local-event-card local-event-single active">',
      '<div class="local-event-label">EVENT</div>',
      '<div class="local-event-title">', esc(shorten(item.title || "Local event", 120)), '</div>',
      item.when ? '<div class="local-event-kv"><span>WHEN</span><b>' + esc(shorten(item.when, 180)) + '</b></div>' : '',
      item.where ? '<div class="local-event-kv"><span>WHERE</span><b>' + esc(shorten(item.where, 160)) + '</b></div>' : '',
      item.source ? '<div class="local-event-kv"><span>HOST</span><b>' + esc(shorten(item.source, 130)) + '</b></div>' : '',
      item.summary ? '<div class="local-event-desc">' + esc(shorten(item.summary, 260)) + '</div>' : '',
      '<div class="local-event-actions">',
      item.url ? '<a class="local-event-link" href="' + esc(item.url) + '" target="_blank" rel="noopener noreferrer">OPEN OFFICIAL LINK</a>' : '<span class="local-event-no-link">NO LINK IN SOURCE</span>',
      '</div></div>'
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
      setTimeout(function () { apply(payload); }, 500);
      setTimeout(function () { apply(payload); }, 1500);
    } catch (e) {
      if (err) err.textContent = "Search failed: " + e.message;
      renderEmpty("LOCAL EVENT SEARCH FAILED · " + e.message);
    } finally {
      if (button) button.disabled = false;
    }
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
      e.stopImmediatePropagation();
      if (modal) modal.hidden = false;
      if (input) {
        input.value = clean(input.value) || "Punggol Singapore";
        setTimeout(function () { input.focus(); input.select(); }, 20);
      }
    }, true);
    if (cancelButton) cancelButton.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (modal) modal.hidden = true;
    }, true);
    if (searchButton) searchButton.addEventListener("click", searchLocalEvents, true);
    if (input) input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") searchLocalEvents(e);
      if (e.key === "Escape" && modal) modal.hidden = true;
    }, true);
    if (prevButton) prevButton.addEventListener("click", function (e) { e.preventDefault(); page -= 1; render(); }, true);
    if (nextButton) nextButton.addEventListener("click", function (e) { e.preventDefault(); page += 1; render(); }, true);
  }
  window.__localEventReload = loadLocalEvents;
  window.__localEventSearch = searchLocalEvents;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bind();
      loadLocalEvents();
      setTimeout(loadLocalEvents, 500);
      setTimeout(loadLocalEvents, 1500);
      setTimeout(loadLocalEvents, 3000);
    });
  } else {
    bind();
    loadLocalEvents();
    setTimeout(loadLocalEvents, 500);
    setTimeout(loadLocalEvents, 1500);
    setTimeout(loadLocalEvents, 3000);
  }
})();
