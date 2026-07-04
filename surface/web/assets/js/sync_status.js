(function () {
  "use strict";

  function id(name) { return document.getElementById(name); }
  function text(value) { return String(value == null ? "" : value).replace(/\s+/g, " ").trim(); }
  function esc(value) {
    return text(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function span(item) { return '<span class="' + esc(item.cls) + '">' + esc(item.label) + '</span>'; }
  function bad(data) { return data && (data.error === "missing_runtime_json" || data.ok === false || data.status === "ERR" || data.status === "FAIL"); }
  function status(name, data) {
    if (bad(data)) return { cls: "sync-fail", label: name + " FAIL" };
    if (Array.isArray(data)) return { cls: data.length ? "sync-ok" : "sync-warn", label: name + " " + data.length };
    if (!data || typeof data !== "object") return { cls: "sync-fail", label: name + " FAIL" };
    if (Array.isArray(data.items)) return { cls: data.items.length ? "sync-ok" : "sync-warn", label: name + " " + data.items.length };
    if (Array.isArray(data.results)) return { cls: data.results.length ? "sync-ok" : "sync-warn", label: name + " " + data.results.length };
    if (data.status === "OK" || data.updated_at || data.temp_c != null) return { cls: "sync-ok", label: name + " OK" };
    return { cls: "sync-warn", label: name + " WAIT" };
  }
  async function probe(name, url) {
    try {
      var response = await fetch(url + "?_=" + Date.now(), { cache: "no-store" });
      if (!response.ok) return { cls: "sync-fail", label: name + " HTTP" + response.status };
      return status(name, await response.json());
    } catch (error) {
      return { cls: "sync-fail", label: name + " FAIL" };
    }
  }
  async function refresh() {
    var tape = id("leftSyncTapeTrack");
    if (!tape) return;
    var items = await Promise.all([
      probe("SCHEDULE", "schedule.json"),
      probe("WEATHER", "weather.json"),
      probe("MARKET", "market.json"),
      probe("NEWS", "event_stream.json"),
      probe("LOCAL", "local_event_search_results.json"),
      probe("PHOTOS", "photos.json")
    ]);
    var hasFail = items.some(function (item) { return item.cls === "sync-fail"; });
    var hasWarn = items.some(function (item) { return item.cls === "sync-warn"; });
    var head = { cls: hasFail ? "sync-fail" : (hasWarn ? "sync-warn" : "sync-ok"), label: hasFail ? "SYNC FAIL" : (hasWarn ? "SYNC WARN" : "SYNC OK") };
    var html = [head].concat(items).map(span).join("");
    tape.innerHTML = html + html;
  }

  document.addEventListener("DOMContentLoaded", function () {
    refresh();
    setInterval(refresh, 60000);
  });
})();
