(function () {
  var items = [];
  var offset = 0;
  var timer = null;
  var empty = true;

  function esc(v) {
    return String(v || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalize(v) {
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

  function cells(text, pad) {
    var raw = normalize(text);
    var n = slotCount();

    if (raw.length > n) raw = raw.slice(0, n);
    if (pad) raw = raw.padEnd(n, " ");

    var html = "";
    for (var i = 0; i < raw.length; i++) {
      var ch = raw[i];
      if (ch === " ") {
        html += '<span class="calendar-board-cell blank">&nbsp;</span>';
      } else {
        html += '<span class="calendar-board-cell">' + esc(ch) + '</span>';
      }
    }
    return html;
  }

  function rowHtml(item) {
    return '<div class="calendar-board-row">' +
      '<div class="calendar-board-time">' + esc(item.time || "") + '</div>' +
      '<div class="calendar-board-event">' + cells(item.title || item.text || "NO SCHEDULE EVENTS", !empty) + '</div>' +
      '</div>';
  }

  function render() {
    var rows = ensure();
    if (!rows) return;

    var list = empty ? [{ time: "", title: "NO SCHEDULE EVENTS" }] : items;
    var n = Math.min(capacity(), list.length);
    var html = "";

    rows.querySelectorAll(".calendar-board-row").forEach(function (r) {
      r.classList.add("flipping");
    });

    for (var i = 0; i < n; i++) {
      html += rowHtml(list[(offset + i) % list.length]);
    }

    setTimeout(function () {
      rows.innerHTML = html;
    }, 120);
  }

  function rotate() {
    if (!empty) {
      var n = Math.min(capacity(), items.length || 1);
      if (items.length > n) offset = (offset + n) % items.length;
    }
    render();
  }

  async function load() {
    try {
      var res = await fetch("schedule.json?_=" + Date.now(), { cache: "no-store" });
      var data = await res.json();
      var events = Array.isArray(data) ? data : (data.events || []);

      items = events.map(function (e) {
        return {
          time: e.time || e.start || e.start_time || e.date || "",
          title: e.text || e.title || e.summary || "Untitled"
        };
      });

      empty = items.length === 0;
      offset = 0;
      render();

      if (timer) clearInterval(timer);
      timer = setInterval(rotate, 7000);
    } catch (err) {
      items = [{ time: "", title: "SCHEDULE ERROR" }];
      empty = true;
      render();
    }
  }

  window.__calendarBoardLoad = load;
  window.loadAgenda = load;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }

  if (window.ResizeObserver) {
    var box = document.getElementById("agendaList");
    if (box) new ResizeObserver(render).observe(box);
  }
})();
