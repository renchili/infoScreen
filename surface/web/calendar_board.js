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
  var ROTATE_MS = 60000;
  var DATA_REFRESH_MS = 30 * 60 * 1000;
  var page = 0;
  var items = [];
  var rotateTimer = null;
  var refreshTimer = null;
  var applying = false;
  var observer = null;
  var resizeObserver = null;
  var lastPayload = null;

  function byId(id) { return document.getElementById(id); }
  function clean(value) { return String(value == null ? "" : value).replace(/\s+/g, " ").trim(); }
  function lower(value) { return clean(value).toLowerCase(); }
  function esc(value) {
    return clean(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
  function short(value, maxLen) {
    var text = clean(value);
    if (!text) return "";
    return text.length <= maxLen ? text : text.slice(0, maxLen - 1).trimEnd() + "…";
  }

  function rows(payload) {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    if (Array.isArray(payload.results)) return payload.results;
    if (Array.isArray(payload.events)) return payload.events;
    if (Array.isArray(payload.items)) return payload.items;
    return [];
  }

  function isPlaceholder(value) {
    var text = lower(value);
    return !text || /^(check official page|open official page|date not published|venue not published|unknown organizer|official source|no link in source)$/i.test(text);
  }

  function badWhere(value) {
    var text = lower(value);
    return !text || isPlaceholder(text) || /\b(free entry|singaporeans|admission|tickets?|exhibitions? in-museum|programmes? in-museum|book your|entry requirements)\b/i.test(text);
  }

  function safeUrl(value) {
    var url = clean(value);
    return /^https?:\/\//i.test(url) ? url : "";
  }

  function first(raw, keys) {
    for (var i = 0; i < keys.length; i++) {
      var value = clean(raw && raw[keys[i]]);
      if (value) return value;
    }
    return "";
  }

  function normalize(raw, index) {
    raw = raw || {};
    var title = first(raw, ["title", "what_text", "name", "event", "summary"]);
    var when = first(raw, ["when", "when_text", "date", "date_text", "time", "time_text", "datetime", "start_time", "start"]);
    var where = first(raw, ["where", "venue", "place", "where_text", "location", "address", "area"]);
    var source = first(raw, ["source_name", "host", "organizer", "who_text", "source"]);
    var summary = first(raw, ["summary", "description", "desc", "why_text", "subtitle"]);
    var url = safeUrl(first(raw, ["url", "link", "href", "official_url"]));
    var order = Number(raw.source_order == null ? raw.source_index : raw.source_order);

    title = title.replace(/\s*-\s*Singapore$/i, "").replace(/\s*\|\s*$/, "");
    if (isPlaceholder(when)) when = "";
    if (badWhere(where)) where = "";
    if (isPlaceholder(source)) source = "";
    if (summary === title || isPlaceholder(summary)) summary = "";

    return { title: title, when: when, where: where, source: source, summary: summary, url: url, sourceOrder: Number.isFinite(order) ? order : index, resultOrder: Number(raw.result_order == null ? index : raw.result_order) };
  }

  function eventKey(item) {
    return item.url || [lower(item.title), lower(item.source), lower(item.when), lower(item.where)].join("|");
  }

  function usable(item) {
    if (!item.title) return false;
    if (/^(official page|local event|events?|overview|view details)$/i.test(item.title)) return false;
    if (/\b(address|opening hours|directions|facilities|venue hire|contact us|about us)\b/i.test(item.title) && !item.summary) return false;
    return true;
  }

  function normalizeList(payload) {
    var map = new Map();
    rows(payload).forEach(function (raw, index) {
      var item = normalize(raw, index);
      if (!usable(item)) return;
      var key = eventKey(item);
      if (!map.has(key)) {
        map.set(key, item);
        return;
      }
      var old = map.get(key);
      if (!old.when && item.when) old.when = item.when;
      if (!old.where && item.where) old.where = item.where;
      if (!old.source && item.source) old.source = item.source;
      if (!old.summary && item.summary) old.summary = item.summary;
      old.sourceOrder = Math.min(old.sourceOrder, item.sourceOrder);
      old.resultOrder = Math.min(old.resultOrder, item.resultOrder);
    });
    return Array.from(map.values()).sort(function (a, b) {
      return (a.sourceOrder - b.sourceOrder) || (a.resultOrder - b.resultOrder);
    });
  }

  function installStyle() {
    if (document.getElementById("local-event-stable-style")) return;
    var style = document.createElement("style");
    style.id = "local-event-stable-style";
    style.textContent = [
      "#localEventList .local-event-card{--le-source-size:11px;--le-title-size:16px;--le-kv-size:12px;--le-kv-label-size:10px;--le-desc-size:11px;--le-link-size:10px;--le-gap:4px;--le-pad-y:8px;--le-pad-x:10px;--le-desc-lines:3;height:100%!important;max-height:100%!important;box-sizing:border-box!important;display:grid!important;grid-template-rows:auto auto auto minmax(0,1fr) auto!important;gap:var(--le-gap)!important;overflow:hidden!important;padding:var(--le-pad-y) var(--le-pad-x) var(--le-pad-y) 12px!important;border-left:3px solid #ffe08a!important;background:rgba(255,224,138,.045)!important;color:#d7ddd9!important;text-decoration:none!important;}",
      "#localEventList .local-event-card.fit-1{--le-source-size:10px;--le-title-size:15px;--le-kv-size:11px;--le-desc-size:10px;--le-link-size:9px;--le-gap:3px;--le-pad-y:7px;--le-desc-lines:2;}",
      "#localEventList .local-event-card.fit-2{--le-source-size:9px;--le-title-size:14px;--le-kv-size:10px;--le-kv-label-size:9px;--le-desc-size:9px;--le-link-size:9px;--le-gap:2px;--le-pad-y:6px;--le-desc-lines:1;}",
      "#localEventList .local-event-card.fit-3{--le-source-size:8px;--le-title-size:13px;--le-kv-size:9px;--le-kv-label-size:8px;--le-desc-size:0px;--le-link-size:8px;--le-gap:2px;--le-pad-y:5px;--le-desc-lines:0;}",
      "#localEventList .local-event-card.fit-4{--le-source-size:8px;--le-title-size:12px;--le-kv-size:8px;--le-kv-label-size:8px;--le-desc-size:0px;--le-link-size:8px;--le-gap:1px;--le-pad-y:4px;--le-desc-lines:0;}",
      "#localEventList .local-event-card.fit-5{--le-source-size:8px;--le-title-size:11px;--le-kv-size:8px;--le-kv-label-size:8px;--le-desc-size:0px;--le-link-size:8px;--le-gap:1px;--le-pad-y:3px;--le-desc-lines:0;}",
      "#localEventList .local-event-source{max-width:calc(100% - 128px)!important;color:#8cecff!important;font-size:var(--le-source-size)!important;line-height:1.08!important;font-weight:950!important;letter-spacing:.08em!important;text-transform:uppercase!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;}",
      "#localEventList .local-event-title{color:#ffe08a!important;font-size:var(--le-title-size)!important;line-height:1.04!important;font-weight:950!important;letter-spacing:.01em!important;overflow:hidden!important;display:-webkit-box!important;-webkit-line-clamp:2!important;-webkit-box-orient:vertical!important;}",
      "#localEventList .local-event-kv{display:grid!important;grid-template-columns:48px minmax(0,1fr)!important;gap:7px!important;align-items:start!important;min-height:0!important;font-size:var(--le-kv-size)!important;line-height:1.08!important;font-weight:850!important;overflow:hidden!important;}",
      "#localEventList .local-event-kv span{color:#7d8782!important;font-size:var(--le-kv-label-size)!important;line-height:1.05!important;font-weight:950!important;letter-spacing:.12em!important;text-transform:uppercase!important;}",
      "#localEventList .local-event-kv b{color:#8cecff!important;font-weight:900!important;overflow:hidden!important;display:-webkit-box!important;-webkit-line-clamp:2!important;-webkit-box-orient:vertical!important;}",
      "#localEventList .local-event-desc{min-height:0!important;max-height:100%!important;overflow:hidden!important;color:#d7ddd9!important;font-size:var(--le-desc-size)!important;line-height:1.08!important;font-weight:760!important;display:-webkit-box!important;-webkit-line-clamp:var(--le-desc-lines)!important;-webkit-box-orient:vertical!important;}",
      "#localEventList .local-event-card.fit-3 .local-event-desc,#localEventList .local-event-card.fit-4 .local-event-desc,#localEventList .local-event-card.fit-5 .local-event-desc{display:none!important;}",
      "#localEventList .local-event-actions{align-self:end!important;min-height:0!important;overflow:hidden!important;}",
      "#localEventList .local-event-link{display:inline-block!important;color:#050606!important;background:#ffe08a!important;border:1px solid #ffe08a!important;border-radius:999px!important;padding:4px 9px!important;font-size:var(--le-link-size)!important;line-height:1!important;font-weight:950!important;letter-spacing:.08em!important;text-decoration:none!important;text-transform:uppercase!important;white-space:nowrap!important;}",
      "#localEventList .local-event-card.fit-3 .local-event-link,#localEventList .local-event-card.fit-4 .local-event-link,#localEventList .local-event-card.fit-5 .local-event-link{padding:3px 8px!important;}",
      "#localEventList .local-event-empty{height:100%!important;display:grid!important;place-items:center!important;color:#7d8782!important;font-size:14px!important;font-weight:900!important;letter-spacing:.05em!important;text-transform:uppercase!important;text-align:center!important;}"
    ].join("\n");
    document.head.appendChild(style);
  }

  function fact(label, value) {
    if (isPlaceholder(value)) return "";
    return '<div class="local-event-kv"><span>' + esc(label) + '</span><b>' + esc(short(value, 180)) + '</b></div>';
  }

  function clearFitClasses(card) {
    for (var i = 1; i <= 5; i++) card.classList.remove("fit-" + i);
  }

  function overflowing(el) {
    return !!(el && (el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2));
  }

  function cardOverflowing(card) {
    if (!card) return false;
    var title = card.querySelector(".local-event-title");
    var desc = card.querySelector(".local-event-desc");
    return overflowing(card) || overflowing(title) || overflowing(desc);
  }

  function fitLocalEventCard() {
    var card = document.querySelector("#localEventList .local-event-card");
    if (!card) return;
    clearFitClasses(card);
    if (!cardOverflowing(card)) return;
    for (var level = 1; level <= 5; level++) {
      clearFitClasses(card);
      card.classList.add("fit-" + level);
      if (!cardOverflowing(card)) return;
    }
  }

  function renderEmpty(text) {
    var list = byId("localEventList");
    var counter = byId("localEventCounter");
    var prev = byId("localEventPrevButton");
    var next = byId("localEventNextButton");
    installStyle();
    applying = true;
    if (list) list.innerHTML = '<div class="local-event-empty">' + esc(text) + '</div>';
    applying = false;
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
    installStyle();
    if (!items.length) {
      var rawCount = lastPayload && typeof lastPayload.count !== "undefined" ? lastPayload.count : rows(lastPayload).length;
      renderEmpty("NO RENDERABLE EVENTS · RAW " + rawCount);
      return;
    }
    if (page < 0) page = items.length - 1;
    if (page >= items.length) page = 0;
    var item = items[page];
    var summary = short(item.summary, 220);
    var html = [
      '<div class="local-event-card active" data-owned-by="calendar-board">',
      '<div class="local-event-source">' + esc(short(item.source || "Official source", 90)) + '</div>',
      '<div class="local-event-title">' + esc(short(item.title || "Local event", 120)) + '</div>',
      fact("WHEN", item.when),
      fact("WHERE", item.where),
      summary ? '<div class="local-event-desc">' + esc(summary) + '</div>' : '<div class="local-event-desc"></div>',
      '<div class="local-event-actions">' + (item.url ? '<a class="local-event-link" href="' + esc(item.url) + '" target="_blank" rel="noopener noreferrer">OPEN OFFICIAL LINK</a>' : '') + '</div>',
      '</div>'
    ].join("");
    applying = true;
    list.innerHTML = html;
    applying = false;
    if (counter) counter.textContent = (page + 1) + "/" + items.length;
    if (prev) prev.disabled = items.length <= 1;
    if (next) next.disabled = items.length <= 1;
    requestAnimationFrame(function () {
      fitLocalEventCard();
      requestAnimationFrame(function () {
        fitLocalEventCard();
        setTimeout(fitLocalEventCard, 60);
      });
    });
  }

  function stopRotate() {
    if (rotateTimer) clearInterval(rotateTimer);
    rotateTimer = null;
  }

  function startRotate() {
    stopRotate();
    if (items.length <= 1) return;
    rotateTimer = setInterval(function () {
      page = (page + 1) % items.length;
      render();
    }, ROTATE_MS);
  }

  function resetRotate() { startRotate(); }

  function apply(payload) {
    lastPayload = payload || {};
    var current = items[page] ? eventKey(items[page]) : "";
    items = normalizeList(payload);
    page = 0;
    if (current) {
      for (var i = 0; i < items.length; i++) {
        if (eventKey(items[i]) === current) {
          page = i;
          break;
        }
      }
    }
    render();
    startRotate();
  }

  async function loadLocalEvents() {
    try {
      var resp = await fetch(API + "?_=" + Date.now(), { cache: "no-store" });
      var payload = await resp.json();
      if (!resp.ok) throw new Error(payload.error || ("HTTP " + resp.status));
      apply(payload);
    } catch (err) {
      renderEmpty("LOCAL EVENTS UNAVAILABLE");
      stopRotate();
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
    stopRotate();
    try {
      var resp = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ location: location, query: location, place: location })
      });
      var payload = await resp.json();
      if (!resp.ok) throw new Error(payload.error || payload.stderr || ("HTTP " + resp.status));
      var modal = byId("localEventModal");
      if (modal) modal.hidden = true;
      if (err) err.textContent = "";
      apply(payload);
    } catch (e) {
      if (err) err.textContent = "Search failed: " + e.message;
      renderEmpty("LOCAL EVENT SEARCH FAILED");
    } finally {
      if (button) button.disabled = false;
    }
  }

  function movePage(delta) {
    if (!items.length) return;
    page += delta;
    render();
    resetRotate();
  }

  function claim(id) {
    var el = byId(id);
    if (!el || !el.parentNode) return el;
    var clone = el.cloneNode(true);
    el.parentNode.replaceChild(clone, el);
    return clone;
  }

  function observeInlineOverwrite() {
    var list = byId("localEventList");
    if (!list || !window.MutationObserver) return;
    if (observer) observer.disconnect();
    observer = new MutationObserver(function () {
      if (applying) return;
      setTimeout(function () {
        var owned = list.querySelector('[data-owned-by="calendar-board"]');
        if (!owned && items.length) render();
      }, 0);
    });
    observer.observe(list, { childList: true, subtree: false });
  }

  function observeResize() {
    var list = byId("localEventList");
    if (!list || !window.ResizeObserver) return;
    if (resizeObserver) resizeObserver.disconnect();
    resizeObserver = new ResizeObserver(function () { fitLocalEventCard(); });
    resizeObserver.observe(list);
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
    observeInlineOverwrite();
    observeResize();
  }

  window.__localEventReload = loadLocalEvents;
  window.__localEventSearch = searchLocalEvents;
  window.__localEventNext = function () { movePage(1); };
  window.__localEventPrev = function () { movePage(-1); };

  function start() {
    bind();
    loadLocalEvents();
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(loadLocalEvents, DATA_REFRESH_MS);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

(function () {
  function byId(id) { return document.getElementById(id); }
  function clean(value) { return String(value == null ? "" : value).replace(/\s+/g, " ").trim(); }

  function installMarketStyle() {
    if (document.getElementById("market-config-style")) return;
    var style = document.createElement("style");
    style.id = "market-config-style";
    style.textContent = [
      ".box[data-title='market'] .inner{display:grid!important;grid-template-rows:minmax(0,1fr) 26px!important;gap:4px!important;min-height:0!important;overflow:hidden!important;}",
      ".box[data-title='market'] .market-list{min-height:0!important;overflow:hidden!important;}",
      ".box[data-title='market'] .market-toolbar{position:static!important;display:flex!important;gap:6px!important;justify-content:flex-end!important;align-items:center!important;background:transparent!important;border-radius:999px!important;height:24px!important;z-index:1!important;}",
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
    var inner = box.querySelector(".inner") || box;
    var toolbar = document.createElement("div");
    toolbar.className = "market-toolbar";
    toolbar.innerHTML = '<button id="marketConfigButton" class="market-config-button" type="button" title="Configure stocks" aria-label="Configure stocks">⚙</button><button id="marketRefreshButton" class="market-config-button" type="button" title="Refresh market" aria-label="Refresh market">↻</button>';
    inner.appendChild(toolbar);

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
