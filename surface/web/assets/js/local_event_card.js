(function () {
  "use strict";

  var API = "/api/local-events/search";
  var allEvents = [];
  var list = [];
  var page = 0;
  var timer = null;
  var rawSignature = null;
  var viewSignature = null;
  var filterSource = localStorage.getItem("local_events_filter_source") || "";
  var filterQuery = localStorage.getItem("local_events_filter_query") || "";
  var newsRaf = null;
  var photoItems = [];
  var photoCursor = 0;
  var photoTimer = null;

  function el(id) { return document.getElementById(id); }
  function txt(v) { return String(v == null ? "" : v).replace(/\s+/g, " ").trim(); }
  function norm(v) { return txt(v).toLocaleLowerCase(); }
  function esc(v) { return txt(v).replace(/[&<>"']/g, function (c) { return { "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[c]; }); }
  function pick(row, keys) { for (var i = 0; i < keys.length; i++) { var v = txt(row && row[keys[i]]); if (v) return v; } return ""; }
  function url(v) { v = txt(v); return v.indexOf("http://") === 0 || v.indexOf("https://") === 0 ? v : ""; }
  function short(v, n) { v = txt(v); return v.length > n ? v.slice(0, n - 1).trim() + "…" : v; }
  function rows(data) { return Array.isArray(data) ? data : ((data && (data.results || data.items || data.events)) || []); }

  function sourceOrderMap(data) {
    var out = {};
    var sources = data && Array.isArray(data.sources) ? data.sources : [];
    sources.forEach(function (row, index) {
      var name = txt(row && (row.title || row.name || row.source_name));
      if (name && out[name] == null) out[name] = index;
    });
    return out;
  }

  function item(row, index, sourceOrders) {
    var title = pick(row, ["title", "what_text", "name", "event", "summary"]);
    var source = pick(row, ["source_name", "institution", "host", "organizer", "source"]);
    var where = pick(row, ["where", "venue", "place", "where_text", "location", "address"]);
    var when = pick(row, ["when_text", "date_text", "time_text", "when", "date", "time", "start"]);
    var summary = pick(row, ["summary", "why_text", "description", "desc"]);
    var configuredOrder = sourceOrders[source];
    var sourceOrder = Number(row && row.source_order != null ? row.source_order : (configuredOrder == null ? 10000 : configuredOrder));
    var resultOrder = Number(row && row.result_order != null ? row.result_order : index);
    if (summary === title || summary === where || summary === source) summary = "";
    return {
      title: title,
      source: source,
      where: where,
      when: when,
      summary: summary,
      link: url(pick(row, ["url", "link", "href", "official_url"])),
      sourceOrder: sourceOrder,
      resultOrder: resultOrder,
      originalIndex: index,
      searchText: norm([title, source, where, when, summary].join(" "))
    };
  }

  function itemKey(row) { return [row.source, row.title, row.when, row.where, row.link].join("\u001f"); }
  function listSignature(items) { return items.map(function (row) { return itemKey(row) + "\u001f" + row.summary; }).join("\u001e"); }
  function clearTimer() { if (timer) { clearInterval(timer); timer = null; } }
  function startTimer() { clearTimer(); if (list.length > 1) timer = setInterval(function () { page = (page + 1) % list.length; draw(); }, 15000); }
  function kv(name, value) { value = txt(value); return value ? '<div class="local-event-kv"><span>' + esc(name) + '</span><b>' + esc(short(value, 150)) + '</b></div>' : ""; }

  function updateNavigationState() {
    var disabled = list.length < 2;
    var prev = el("localEventPrevButton");
    var next = el("localEventNextButton");
    if (prev) prev.disabled = disabled;
    if (next) next.disabled = disabled;
  }

  function drawEmpty(message) {
    var box = el("localEventList");
    if (box) box.innerHTML = '<div class="local-event-empty">' + esc(message) + '</div>';
    var c = el("localEventCounter");
    if (c) c.textContent = allEvents.length ? "0/" + allEvents.length : "";
    updateNavigationState();
  }

  function fitDescription() {
    var box = el("localEventList");
    var desc = box && box.querySelector(".local-event-desc");
    var text = desc && desc.querySelector(".local-event-desc-text");
    if (!desc || !text) return;
    var full = desc.dataset.fullText || text.textContent || "";
    text.textContent = full;
    var lineHeight = parseFloat(getComputedStyle(text).lineHeight) || 0;
    var available = desc.clientHeight;
    var maxLines = lineHeight > 0 ? Math.floor(Math.max(0, available - 2) / lineHeight) : 0;
    var maxHeight = maxLines * lineHeight;
    if (!full || maxLines < 1) { text.textContent = ""; return; }
    function fits(value) { text.textContent = value; return text.getBoundingClientRect().height <= maxHeight + 0.25; }
    if (fits(full)) return;
    var low = 0;
    var high = full.length;
    while (low < high) {
      var mid = Math.ceil((low + high) / 2);
      var candidate = full.slice(0, mid).trim();
      if (fits(candidate + "…")) low = mid;
      else high = mid - 1;
    }
    var fitted = full.slice(0, low).trim();
    text.textContent = fitted ? fitted + "…" : "";
  }

  function scheduleDescriptionFit() { requestAnimationFrame(function () { requestAnimationFrame(fitDescription); }); }

  function draw() {
    var box = el("localEventList");
    if (!box) return;
    if (!list.length) {
      drawEmpty(allEvents.length ? "NO EVENTS MATCH FILTER" : "NO LOCAL EVENTS AVAILABLE");
      return;
    }
    if (page < 0) page = list.length - 1;
    if (page >= list.length) page = 0;
    var x = list[page];
    box.innerHTML = '<div class="local-event-card local-event-single active"><div class="local-event-source-top">' + esc(short(x.source || "Official source", 96)) + '</div><div class="local-event-title">' + esc(short(x.title || "Local event", 110)) + '</div>' + kv("WHEN", x.when || "Check official page") + kv("WHERE", x.where || "Check official page") + (x.summary ? '<div class="local-event-desc"><div class="local-event-desc-text">' + esc(x.summary) + '</div></div>' : "") + '<div class="local-event-actions">' + (x.link ? '<a class="local-event-link" href="' + esc(x.link) + '" target="_blank" rel="noopener noreferrer">OPEN OFFICIAL LINK</a>' : '<span class="local-event-no-link">NO LINK IN SOURCE</span>') + '</div></div>';
    var desc = box.querySelector(".local-event-desc");
    if (desc) { desc.dataset.fullText = x.summary; scheduleDescriptionFit(); }
    var c = el("localEventCounter");
    if (c) c.textContent = (page + 1) + "/" + list.length;
    updateNavigationState();
  }

  function institutionNames() {
    var seen = {};
    return allEvents.filter(function (row) {
      if (!row.source || seen[row.source]) return false;
      seen[row.source] = true;
      return true;
    }).sort(function (a, b) {
      return a.sourceOrder - b.sourceOrder || a.source.localeCompare(b.source);
    }).map(function (row) { return row.source; });
  }

  function populateInstitutionFilter() {
    var select = el("localEventInstitutionSelect");
    if (!select) return;
    var names = institutionNames();
    if (filterSource && names.indexOf(filterSource) < 0) {
      filterSource = "";
      localStorage.removeItem("local_events_filter_source");
    }
    select.innerHTML = '<option value="">All institutions</option>' + names.map(function (name) {
      return '<option value="' + esc(name) + '">' + esc(name) + '</option>';
    }).join("");
    select.value = filterSource;
  }

  function filterTerms() {
    return norm(filterQuery).split(/\s+/).filter(Boolean);
  }

  function applyFilters(preserveCurrent) {
    var currentKey = preserveCurrent && list[page] ? itemKey(list[page]) : "";
    var terms = filterTerms();
    var nextList = allEvents.filter(function (row) {
      if (filterSource && row.source !== filterSource) return false;
      return !terms.length || terms.every(function (term) { return row.searchText.indexOf(term) >= 0; });
    });
    var nextSignature = listSignature(nextList);
    list = nextList;
    if (currentKey) {
      var matched = list.findIndex(function (row) { return itemKey(row) === currentKey; });
      page = matched >= 0 ? matched : Math.min(page, Math.max(0, list.length - 1));
    } else {
      page = 0;
    }
    if (nextSignature !== viewSignature) viewSignature = nextSignature;
    draw();
    startTimer();
  }

  function apply(data, preserveCurrent) {
    var sourceOrders = sourceOrderMap(data);
    var nextAll = rows(data).map(function (row, index) {
      return item(row, index, sourceOrders);
    }).sort(function (a, b) {
      return a.sourceOrder - b.sourceOrder || a.resultOrder - b.resultOrder || a.originalIndex - b.originalIndex;
    });
    var nextSignature = listSignature(nextAll);
    if (nextSignature === rawSignature) return false;
    allEvents = nextAll;
    rawSignature = nextSignature;
    populateInstitutionFilter();
    applyFilters(preserveCurrent);
    return true;
  }

  function load() {
    fetch(API, { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) { apply(data, true); })
      .catch(function () { if (!allEvents.length) drawEmpty("LOCAL EVENTS UNAVAILABLE"); });
  }

  function filterStatusText() {
    return "Showing " + list.length + " of " + allEvents.length + " events";
  }

  function openModal() {
    var modal = el("localEventModal");
    var input = el("localEventFilterInput");
    var select = el("localEventInstitutionSelect");
    var status = el("localEventModalError");
    populateInstitutionFilter();
    if (input) input.value = filterQuery;
    if (select) select.value = filterSource;
    if (status) status.textContent = filterStatusText();
    if (modal) modal.hidden = false;
    if (select) select.focus();
  }

  function closeModal() {
    var modal = el("localEventModal");
    if (modal) modal.hidden = true;
  }

  function runSearch() {
    var input = el("localEventFilterInput");
    var select = el("localEventInstitutionSelect");
    filterQuery = txt(input && input.value);
    filterSource = txt(select && select.value);
    if (filterQuery) localStorage.setItem("local_events_filter_query", filterQuery);
    else localStorage.removeItem("local_events_filter_query");
    if (filterSource) localStorage.setItem("local_events_filter_source", filterSource);
    else localStorage.removeItem("local_events_filter_source");
    applyFilters(false);
    closeModal();
  }

  function ageText(seconds) { return seconds < 60 ? seconds + "s" : Math.floor(seconds / 60) + "m" + (seconds % 60) + "s"; }
  function latestText(date) { return date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
  function fileStatus(path, label, limit) { return fetch(path + "?_=" + Date.now(), { method: "HEAD", cache: "no-store" }).then(function (r) { var lm = r.headers.get("Last-Modified"); if (!r.ok || !lm) return { label: label, ok: false, state: "MISS", age: "--", latest: "--" }; var d = new Date(lm); var seconds = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000)); var ok = seconds <= limit; return { label: label, ok: ok, state: ok ? "OK" : "STALE", age: ageText(seconds), latest: latestText(d) }; }).catch(function () { return { label: label, ok: false, state: "ERR", age: "--", latest: "--" }; }); }
  function loadSyncStatus() { var tape = el("leftSyncTapeTrack"); if (!tape) return; Promise.all([fileStatus("schedule.json", "SCHEDULE", 600), fileStatus("weather.json", "WEATHER", 900), fileStatus("market.json", "MARKET", 600), fileStatus("event_stream.json", "NEWS", 600)]).then(function (items) { var html = items.map(function (x) { var cls = x.ok ? "sync-ok" : (x.state === "STALE" ? "sync-warn" : "sync-fail"); var icon = x.ok ? "●" : (x.state === "STALE" ? "▲" : "■"); return '<span class="' + cls + '">' + icon + " " + esc(x.label) + " " + esc(x.state) + '</span><span class="sync-muted">LATEST ' + esc(x.latest) + '</span><span class="sync-muted">AGE ' + esc(x.age) + "</span>"; }).join(""); tape.innerHTML = html + html; }); }
  function newsItem(label, row) { return '<span class="news-item"><span class="news-source">' + esc(label) + '</span><span class="news-title">' + esc(row && (row.title || row.text || row.summary) || "Untitled") + '</span><span class="news-sep">◆</span></span>'; }
  function fillNews(trackId, label, items) { var track = el(trackId); if (!track) return; items = Array.isArray(items) && items.length ? items : [{ title: "event_stream.json not loaded" }]; var block = ""; for (var i = 0; i < 8; i++) block += newsItem(label, items[i % items.length]); track.innerHTML = block + block; }
  function startNewsTicker() { var tracks = [el("newsTickerTrackEN"), el("newsTickerTrackFR"), el("newsTickerTrackZH")].filter(Boolean); if (tracks.length !== 3) return; if (newsRaf) cancelAnimationFrame(newsRaf); var start = performance.now(); function frame(now) { var x = -((((now - start) / 1000) * 48) % (760 * 8)); tracks.forEach(function (t) { t.style.transform = "translate3d(" + x + "px,0,0)"; }); newsRaf = requestAnimationFrame(frame); } newsRaf = requestAnimationFrame(frame); }
  function repairNews() { fetch("event_stream.json?_=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (data) { var g = data.items_by_lang || {}; fillNews("newsTickerTrackEN", "EN", g.en || []); fillNews("newsTickerTrackFR", "FR", g.fr || []); fillNews("newsTickerTrackZH", "中文", g.zh || []); startNewsTicker(); }).catch(function () { fillNews("newsTickerTrackEN", "ERR", [{ title: "event_stream.json not loaded" }]); fillNews("newsTickerTrackFR", "ERR", [{ title: "check fetch_event_stream.py" }]); fillNews("newsTickerTrackZH", "ERR", [{ title: "等待下一次刷新" }]); startNewsTicker(); }); }
  function shuffle(a) { a = a.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function showPhoto() { var card = el("photoSingleCard"), inner = el("photoSingleInner"), caption = el("photoSingleCaption"); if (!card || !inner || !caption || !photoItems.length) return; var x = photoItems[photoCursor % photoItems.length]; photoCursor++; if (!x || !x.src) return; card.classList.add("flipping"); setTimeout(function () { inner.style.backgroundImage = "url('" + String(x.src).replace(/'/g, "%27") + "')"; caption.textContent = x.name || ""; card.classList.remove("flipping"); }, 310); }
  function repairPhotoWall() { var wall = el("photoFlipWall"); if (!wall) return; fetch("photos.json?_=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (data) { var items = Array.isArray(data.items) ? data.items : []; if (!items.length) { wall.innerHTML = '<div class="photo-flip-empty">ADD PHOTOS TO ~/infoscreen/surface/.env/photos</div>'; return; } photoItems = shuffle(items); photoCursor = 0; wall.innerHTML = '<div class="photo-single-card" id="photoSingleCard"><div class="photo-single-inner" id="photoSingleInner"></div><div class="photo-single-caption" id="photoSingleCaption"></div></div>'; showPhoto(); if (photoTimer) clearInterval(photoTimer); if (photoItems.length > 1) photoTimer = setInterval(showPhoto, 9000); }).catch(function () { wall.innerHTML = '<div class="photo-flip-empty">photos.json not loaded</div>'; }); }

  document.addEventListener("DOMContentLoaded", function () {
    var prev = el("localEventPrevButton");
    var next = el("localEventNextButton");
    var filterButton = el("localEventLocationButton");
    var cancel = el("localEventCancelButton");
    var submit = el("localEventSearchButton");
    var input = el("localEventFilterInput");
    var modal = el("localEventModal");
    if (prev) prev.onclick = function () { clearTimer(); page--; draw(); startTimer(); };
    if (next) next.onclick = function () { clearTimer(); page++; draw(); startTimer(); };
    if (filterButton) filterButton.onclick = openModal;
    if (cancel) cancel.onclick = closeModal;
    if (submit) submit.onclick = runSearch;
    if (input) input.onkeydown = function (e) { if (e.key === "Enter") runSearch(); if (e.key === "Escape") closeModal(); };
    if (modal) modal.onclick = function (e) { if (e.target === modal) closeModal(); };
    window.addEventListener("resize", scheduleDescriptionFit);
    load();
    loadSyncStatus();
    repairNews();
    repairPhotoWall();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleDescriptionFit);
    setInterval(load, 15000);
    setInterval(loadSyncStatus, 60000);
    setInterval(repairNews, 300000);
    setInterval(repairPhotoWall, 300000);
  });
})();
