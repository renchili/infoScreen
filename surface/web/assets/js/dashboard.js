(function () {
  "use strict";

  var start = Date.now();
  function id(name) { return document.getElementById(name); }
  function text(value) { return String(value == null ? "" : value).replace(/\s+/g, " ").trim(); }
  function html(value) {
    return text(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function pad(value) { return String(value).padStart(2, "0"); }
  function dir(value) {
    var v = text(value || "N/A");
    if (!v || v === "N/A" || v === "--") return "flat";
    return v.charAt(0) === "-" ? "down" : "up";
  }
  function arrow(direction) { return direction === "down" ? "▼" : (direction === "up" ? "▲" : "◆"); }
  function price(item) {
    var raw = item && item.price;
    if (raw == null || raw === "" || raw === "N/D") return "N/A";
    raw = String(raw);
    return raw.charAt(0) === "$" ? raw : "$" + raw;
  }

  function updateClock() {
    var now = new Date();
    var t = id("time");
    var d = id("date");
    var r = id("refresh");
    var u = id("uptime");
    if (t) t.textContent = pad(now.getHours()) + ":" + pad(now.getMinutes());
    if (d) d.textContent = now.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" });
    if (r) r.textContent = pad(now.getHours()) + ":" + pad(now.getMinutes());
    if (u) {
      var diff = Math.floor((Date.now() - start) / 1000);
      u.textContent = pad(Math.floor(diff / 3600)) + ":" + pad(Math.floor((diff % 3600) / 60));
    }
  }

  function marketRow(item) {
    var pct = text(item.percent || item.change_percent || item.change || "N/A");
    var direction = dir(pct);
    var session = text(item.session);
    return '<div class="market-row"><span class="ticker">' + html(item.symbol || "--") + '</span><span class="price ' + direction + '"><span class="market-arrow">' + arrow(direction) + '</span> ' + html(price(item)) + (session ? '<span class="market-session"> ' + html(session) + '</span>' : '') + '</span><span class="chg ' + direction + '">' + html(pct) + '</span></div>';
  }

  function marketTapeItem(item) {
    var pct = text(item.percent || item.change_percent || item.change || "N/A");
    var direction = dir(pct);
    var session = text(item.session);
    return '<span class="market-tape-item"><span class="symbol">' + html(item.symbol || "--") + '</span><span class="price ' + direction + '"><span class="market-arrow">' + arrow(direction) + '</span> ' + html(price(item)) + '</span>' + (session ? '<span class="session">' + html(session) + '</span>' : '') + '<span class="' + direction + '">' + arrow(direction) + ' ' + html(pct) + '</span></span>';
  }

  function renderMarketTape(items) {
    var tape = id("globalMarketTapeTrack");
    if (!tape) return;
    var parts = items.slice(0, 10).map(marketTapeItem);
    tape.innerHTML = parts.join("") + parts.join("");
  }

  async function loadMarket() {
    var box = id("marketList");
    try {
      var response = await fetch("market.json?_=" + Date.now(), { cache: "no-store" });
      var data = await response.json();
      var items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) throw new Error("empty market data");
      if (box) box.innerHTML = items.slice(0, 6).map(marketRow).join("") + '<div class="market-foot">source: ' + html(data.source || "market") + ' · ' + html(data.updated_at || "") + '</div>';
      renderMarketTape(items);
    } catch (error) {
      if (box) box.innerHTML = '<div class="market-row"><span class="ticker">ERR</span><span class="price down"><span class="market-arrow">▼</span> market.json</span><span class="chg down">FAIL</span></div><div class="market-foot">check Surface timer</div>';
      var tape = id("globalMarketTapeTrack");
      if (tape) tape.innerHTML = '<span class="flat">MARKET DATA FAILED</span><span class="flat">CHECK market.json</span><span class="down">SURFACE TIMER ERROR</span><span class="flat">MARKET DATA FAILED</span><span class="flat">CHECK market.json</span><span class="down">SURFACE TIMER ERROR</span>';
    }
  }

  function loadTopMarketTape() { return loadMarket(); }

  async function loadWeather() {
    var temp = id("weatherTemp");
    var desc = id("weatherDesc");
    try {
      var response = await fetch("weather.json?_=" + Date.now(), { cache: "no-store" });
      var data = await response.json();
      if (temp) temp.textContent = (data.temp_c == null ? "--" : data.temp_c) + "°C";
      if (desc) desc.innerHTML = html(data.location || "Singapore") + "<br />" + html(data.desc || "unknown") + " / humidity " + html(data.humidity || "--") + "%<br />feels " + html(data.feels_like_c || "--") + "°C · " + html(data.source || "local");
    } catch (error) {
      if (temp) temp.textContent = "--°C";
      if (desc) desc.innerHTML = "weather.json not loaded<br />check Surface timer";
    }
  }

  function updateDemoMetrics() {
    [["cpuBar", "cpuText", 10 + Math.floor(Math.random() * 35), "%"], ["memBar", "memText", 42 + Math.floor(Math.random() * 26), "%"], ["diskBar", "diskText", 38 + Math.floor(Math.random() * 10), "%"], ["netBar", "netText", 70 + Math.floor(Math.random() * 20), "OK"]].forEach(function (row) {
      var bar = id(row[0]);
      var label = id(row[1]);
      if (bar) bar.style.width = row[2] + "%";
      if (label) label.textContent = row[3] === "%" ? row[2] + "%" : row[3];
    });
  }

  window.loadMarket = loadMarket;
  window.loadTopMarketTape = loadTopMarketTape;
  window.loadWeather = loadWeather;

  document.addEventListener("DOMContentLoaded", function () {
    updateClock();
    updateDemoMetrics();
    loadWeather();
    loadMarket();
    setInterval(updateClock, 1000);
    setInterval(updateDemoMetrics, 6000);
    setInterval(loadWeather, 300000);
    setInterval(loadMarket, 60000);
  });
})();
