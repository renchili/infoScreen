(function () {
  "use strict";
  var DEFAULT_SYMBOLS = ["AAPL", "NVDA", "MSFT", "TSLA"];

  function byId(id) { return document.getElementById(id); }
  function parseSymbols(value) {
    return String(value || "")
      .split(/[,\s]+/)
      .map(function (s) { return s.trim().toUpperCase(); })
      .filter(Boolean)
      .filter(function (s, i, arr) { return arr.indexOf(s) === i; })
      .slice(0, 12);
  }
  function setStatus(message) {
    var el = byId("marketCustomStatus");
    if (el) el.textContent = message;
  }
  async function getConfig() {
    try {
      var res = await fetch("/api/market-config?_=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("api " + res.status);
      var data = await res.json();
      var symbols = Array.isArray(data.symbols) ? data.symbols : [];
      return symbols.length ? symbols : DEFAULT_SYMBOLS;
    } catch (error) {
      var local = parseSymbols(localStorage.getItem("market_symbols") || "");
      return local.length ? local : DEFAULT_SYMBOLS;
    }
  }
  async function saveConfig(symbols) {
    localStorage.setItem("market_symbols", symbols.join(","));
    var res = await fetch("/api/market-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols: symbols })
    });
    if (!res.ok) throw new Error("save failed " + res.status);
    return res.json();
  }
  async function refreshMarket() {
    var res = await fetch("/api/market-refresh", { method: "POST" });
    if (!res.ok) throw new Error("refresh failed " + res.status);
    await res.json();
    if (window.loadMarket) await window.loadMarket();
  }
  async function initMarketCustom() {
    var list = byId("marketList");
    if (!list || byId("marketConfigButton")) return;
    var host = list.parentElement;
    if (!host) return;
    var panel = document.createElement("div");
    panel.className = "market-custom-panel";
    panel.hidden = true;
    panel.innerHTML = '<input id="marketSymbolsInput" spellcheck="false" autocomplete="off" placeholder="AAPL, NVDA, MSFT"><button id="marketSaveBtn">SAVE</button><button id="marketRefreshBtn">REFRESH</button><div class="market-custom-status" id="marketCustomStatus"></div>';
    var button = document.createElement("button");
    button.id = "marketConfigButton";
    button.className = "market-config-button";
    button.type = "button";
    button.textContent = "⚙";
    button.title = "Market symbols";
    button.setAttribute("aria-label", "Market symbols");
    host.insertBefore(button, list);
    host.insertBefore(panel, list);
    var input = byId("marketSymbolsInput");
    var save = byId("marketSaveBtn");
    var refresh = byId("marketRefreshBtn");
    var symbols = await getConfig();
    input.value = symbols.join(", ");
    setStatus("symbols: " + symbols.join(", "));
    button.onclick = function () { panel.hidden = !panel.hidden; };
    save.onclick = async function () {
      var next = parseSymbols(input.value);
      if (!next.length) { setStatus("empty symbols"); return; }
      try {
        setStatus("saving...");
        await saveConfig(next);
        await refreshMarket();
        setStatus("saved");
      } catch (error) {
        setStatus("save failed: " + error.message);
      }
    };
    refresh.onclick = async function () {
      try {
        setStatus("refreshing...");
        await refreshMarket();
        setStatus("refreshed");
      } catch (error) {
        setStatus("refresh failed: " + error.message);
      }
    };
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMarketCustom);
  } else {
    initMarketCustom();
  }
})();
