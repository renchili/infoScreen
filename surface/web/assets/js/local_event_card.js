(function () {
  "use strict";

  var api = "/api/local-events/search";
  var list = [];
  var page = 0;
  var currentLocation = localStorage.getItem("local_events_location") || "Punggol Singapore";

  function el(id) { return document.getElementById(id); }
  function txt(v) { return String(v == null ? "" : v).replace(/\s+/g, " ").trim(); }
  function enc(v) { return txt(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#39;"); }
  function rows(data) { return Array.isArray(data) ? data : ((data && (data.results || data.items || data.events)) || []); }
  function val(row, keys) { for (var i = 0; i < keys.length; i++) { var v = txt(row && row[keys[i]]); if (v) return v; } return ""; }
  function okurl(v) { v = txt(v); return /^https?:\/\//i.test(v) ? v : ""; }
  function item(row, i) {
    return {
      title: val(row, ["title", "what_text", "name", "event"]),
      when: val(row, ["when", "when_text", "date", "date_text", "time", "time_text"]),
      where: val(row, ["where", "venue", "place", "where_text", "location"]),
      source: val(row, ["source_name", "host", "organizer", "source"]),
      summary: val(row, ["summary", "description", "desc", "why_text"]),
      link: okurl(val(row, ["url", "link", "href", "official_url"])),
      order: Number(row && (row.source_order == null ? i : row.source_order))
    };
  }
  function fact(k, v) { v = txt(v); return v ? '<div class="local-event-kv"><span>' + enc(k) + '</span><b>' + enc(v) + '</b></div>' : ""; }
  function setCounter() { var c = el("localEventCounter"); if (c) c.textContent = list.length ? ((page + 1) + "/" + list.length) : "0/0"; }
  function drawEmpty(v) { var box = el("localEventList"); if (box) box.innerHTML = '<div class="local-event-empty">' + enc(v) + '</div>'; setCounter(); }
  function draw() {
    var box = el("localEventList");
    if (!box) return;
    if (!list.length) return drawEmpty("NO RENDERABLE EVENTS");
    if (page < 0) page = list.length - 1;
    if (page >= list.length) page = 0;
    var x = list[page];
    var action = x.link ? '<a class="local-event-link" href="' + enc(x.link) + '" target="_blank" rel="noopener">OFFICIAL</a>' : '<span class="local-event-no-link">OFFICIAL SOURCE</span>';
    box.innerHTML = '<div class="local-event-card active">' +
      '<div class="local-event-source">' + enc(x.source || "Official source") + '</div>' +
      '<div class="local-event-title">' + enc(x.title || "Local event") + '</div>' +
      '<div class="local-event-facts">' + fact("WHEN", x.when) + fact("WHERE", x.where) + '</div>' +
      '<div class="local-event-desc"><div class="local-event-desc-text">' + enc(x.summary || "") + '</div></div>' +
      '<div class="local-event-actions">' + action + '</div>' +
      '</div>';
    setCounter();
  }
  function normalize(data) {
    return rows(data).map(item).filter(function (x) { return x.title; }).sort(function (a, b) { return (a.order || 0) - (b.order || 0); });
  }
  function load() {
    drawEmpty("LOADING LOCAL EVENTS");
    fetch(api + "?_=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) { list = normalize(data); page = 0; draw(); })
      .catch(function () { drawEmpty("LOCAL EVENTS UNAVAILABLE"); });
  }
  function search(location) {
    drawEmpty("SEARCHING LOCAL EVENTS");
    return fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ location: location })
    }).then(function (r) { return r.json(); }).then(function (data) {
      currentLocation = location;
      localStorage.setItem("local_events_location", location);
      list = normalize(data);
      page = 0;
      draw();
    });
  }
  function openModal() {
    var modal = el("localEventModal");
    var input = el("localEventLocationInput");
    var err = el("localEventModalError");
    if (err) err.textContent = "";
    if (input) input.value = currentLocation;
    if (modal) modal.hidden = false;
    if (input) input.focus();
  }
  function closeModal() { var modal = el("localEventModal"); if (modal) modal.hidden = true; }
  function runModalSearch() {
    var input = el("localEventLocationInput");
    var button = el("localEventSearchButton");
    var err = el("localEventModalError");
    var location = txt(input && input.value) || "Punggol Singapore";
    if (button) button.disabled = true;
    if (err) err.textContent = "searching...";
    search(location).then(function () { closeModal(); }).catch(function (e) {
      if (err) err.textContent = e && e.message ? e.message : "search failed";
    }).finally(function () { if (button) button.disabled = false; });
  }

  function syncSpan(item) { return '<span class="' + enc(item.cls) + '">' + enc(item.label) + '</span>'; }
  function bad(data) { return data && (data.error === "missing_runtime_json" || data.ok === false || data.status === "ERR"); }
  function status(name, data) {
    if (bad(data)) return { cls: "sync-fail", label: name + " FAIL" };
    if (Array.isArray(data)) return { cls: data.length ? "sync-ok" : "sync-warn", label: name + " " + data.length };
    if (!data || typeof data !== "object") return { cls: "sync-fail", label: name + " FAIL" };
    if (Array.isArray(data.items)) return { cls: data.items.length ? "sync-ok" : "sync-warn", label: name + " " + data.items.length };
    if (Array.isArray(data.results)) return { cls: data.results.length ? "sync-ok" : "sync-warn", label: name + " " + data.results.length };
    if (data.status === "OK" || data.updated_at || data.temp_c != null) return { cls: "sync-ok", label: name + " OK" };
    return { cls: "sync-warn", label: name + " WAIT" };
  }
  function probe(name, path) {
    return fetch(path + "?_=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("http"); return r.json(); })
      .then(function (data) { return status(name, data); })
      .catch(function () { return { cls: "sync-fail", label: name + " FAIL" }; });
  }
  function refreshSync() {
    var tape = el("leftSyncTapeTrack");
    if (!tape) return;
    Promise.all([
      probe("SCHEDULE", "schedule.json"),
      probe("WEATHER", "weather.json"),
      probe("MARKET", "market.json"),
      probe("NEWS", "event_stream.json"),
      probe("LOCAL", "local_event_search_results.json"),
      probe("PHOTOS", "photos.json")
    ]).then(function (items) {
      var fail = items.some(function (x) { return x.cls === "sync-fail"; });
      var warn = items.some(function (x) { return x.cls === "sync-warn"; });
      var head = { cls: fail ? "sync-fail" : (warn ? "sync-warn" : "sync-ok"), label: fail ? "SYNC FAIL" : (warn ? "SYNC WARN" : "SYNC OK") };
      var html = [head].concat(items).map(syncSpan).join("");
      tape.innerHTML = html + html;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var prev = el("localEventPrevButton");
    var next = el("localEventNextButton");
    var locate = el("localEventLocationButton");
    var cancel = el("localEventCancelButton");
    var submit = el("localEventSearchButton");
    var input = el("localEventLocationInput");
    if (prev) prev.onclick = function () { page--; draw(); };
    if (next) next.onclick = function () { page++; draw(); };
    if (locate) locate.onclick = openModal;
    if (cancel) cancel.onclick = closeModal;
    if (submit) submit.onclick = runModalSearch;
    if (input) input.onkeydown = function (event) { if (event.key === "Enter") runModalSearch(); if (event.key === "Escape") closeModal(); };
    load();
    refreshSync();
    setInterval(refreshSync, 60000);
  });
})();
