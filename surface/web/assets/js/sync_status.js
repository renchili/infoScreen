(function () {
  "use strict";
  function el(id) { return document.getElementById(id); }
  function clean(value) { return String(value || "").replace(/\s+/g, " ").trim(); }
  function esc(value) { return clean(value).replace(/[&<>"']/g, function (ch) { return { "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[ch]; }); }
  function ageText(seconds) { return seconds < 60 ? seconds + "s" : Math.floor(seconds / 60) + "m" + (seconds % 60) + "s"; }
  function latestText(date) { return date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
  function fileStatus(path, label, limitSeconds) {
    return fetch(path + "?_=" + Date.now(), { method: "HEAD", cache: "no-store" }).then(function (res) {
      var lm = res.headers.get("Last-Modified");
      if (!res.ok || !lm) return { label: label, ok: false, state: "MISS", age: "--", latest: "--" };
      var date = new Date(lm);
      var seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
      var ok = seconds <= limitSeconds;
      return { label: label, ok: ok, state: ok ? "OK" : "STALE", age: ageText(seconds), latest: latestText(date) };
    }).catch(function () {
      return { label: label, ok: false, state: "ERR", age: "--", latest: "--" };
    });
  }
  function render(items) {
    var tape = el("leftSyncTapeTrack");
    if (!tape) return;
    var html = items.map(function (x) {
      var cls = x.ok ? "sync-ok" : (x.state === "STALE" ? "sync-warn" : "sync-fail");
      var icon = x.ok ? "●" : (x.state === "STALE" ? "▲" : "■");
      return '<span class="' + cls + '">' + icon + ' ' + esc(x.label) + ' ' + esc(x.state) + '</span>' +
        '<span class="sync-muted">LATEST ' + esc(x.latest) + '</span>' +
        '<span class="sync-muted">AGE ' + esc(x.age) + '</span>';
    }).join("");
    tape.innerHTML = html + html;
  }
  function loadSyncStatus() {
    Promise.all([
      fileStatus("schedule.json", "SCHEDULE", 600),
      fileStatus("weather.json", "WEATHER", 900),
      fileStatus("market.json", "MARKET", 600),
      fileStatus("event_stream.json", "NEWS", 600)
    ]).then(render);
  }
  document.addEventListener("DOMContentLoaded", function () {
    loadSyncStatus();
    setInterval(loadSyncStatus, 60000);
  });
  window.loadSyncStatus = loadSyncStatus;
})();
