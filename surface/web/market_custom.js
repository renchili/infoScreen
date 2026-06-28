(function () {
  var DEFAULT_SYMBOLS = ["AAPL", "NVDA", "MSFT", "TSLA"];

  function esc(v) {
    return String(v || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function parseSymbols(v) {
    return String(v || "")
      .split(/[,\s]+/)
      .map(function (s) { return s.trim().toUpperCase(); })
      .filter(Boolean)
      .filter(function (s, i, arr) { return arr.indexOf(s) === i; })
      .slice(0, 12);
  }

  function status(msg) {
    var el = document.getElementById("marketCustomStatus");
    if (el) el.textContent = msg;
  }

  async function getConfig() {
    try {
      var res = await fetch("/api/market-config?_=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("api " + res.status);
      var data = await res.json();
      var symbols = Array.isArray(data.symbols) ? data.symbols : [];
      return symbols.length ? symbols : DEFAULT_SYMBOLS;
    } catch (e) {
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
    try {
      status("refreshing market...");
      var res = await fetch("/api/market-refresh", { method: "POST" });
      if (!res.ok) throw new Error("refresh failed " + res.status);
      await res.json();
      if (window.loadMarket) await window.loadMarket();
      status("saved and refreshed");
    } catch (e) {
      status("saved, refresh failed: " + e.message);
    }
  }

  async function initMarketCustom() {
    var list = document.getElementById("marketList");
    if (!list || document.getElementById("marketSymbolsInput")) return;

    var panel = document.createElement("div");
    panel.className = "market-custom";
    panel.innerHTML =
      '<input id="marketSymbolsInput" spellcheck="false" autocomplete="off" placeholder="AAPL, NVDA, MSFT">' +
      '<button id="marketSaveBtn">SAVE</button>' +
      '<button id="marketRefreshBtn">REFRESH</button>' +
      '<div class="market-custom-status" id="marketCustomStatus">loading symbols...</div>';

    list.parentNode.insertBefore(panel, list);

    var input = document.getElementById("marketSymbolsInput");
    var save = document.getElementById("marketSaveBtn");
    var refresh = document.getElementById("marketRefreshBtn");

    var symbols = await getConfig();
    input.value = symbols.join(", ");
    status("symbols: " + symbols.join(", "));

    save.onclick = async function () {
      var next = parseSymbols(input.value);
      if (!next.length) {
        status("empty symbols");
        return;
      }
      try {
        status("saving...");
        await saveConfig(next);
        await refreshMarket();
      } catch (e) {
        status("save failed: " + e.message);
      }
    };

    refresh.onclick = refreshMarket;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMarketCustom);
  } else {
    initMarketCustom();
  }
})();
