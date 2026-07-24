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
    
    var html = "";
    for (var i = 0; i < raw.length; i++) {
      var ch = raw[i];
      if (ch === " ") {
        html += '<span class="calendar-board-cell blank">&nbsp;</span>';
      } else {
        html += '<span class="calendar-board-cell" data-final="' + esc(ch) + '">' + esc(ch) + '</span>';
      }
    }
    return html;
  }

  function rowHtml(item) {
    return '<div class="calendar-board-row">' +
      '<div class="calendar-board-time">' + cells(item.time || "", false) + '</div>' +
      '<div class="calendar-board-event">' + cells(item.title || item.text || "NO SCHEDULE EVENTS", false) + '</div>' +
      '</div>';
  }

  function animateBoard(rows) {
    var cells = Array.prototype.slice.call(
      rows.querySelectorAll(".calendar-board-cell:not(.blank)")
    );

    cells.forEach(function (cell, idx) {
      var finalChar = cell.getAttribute("data-final") || cell.textContent || "";
      var delay = idx * 95;

      later(function () {
        var step = 0;
        cell.classList.add("flipping");
        cell.textContent = "A";

        var id = tick(function () {
          if (step < CHARSET.length) {
            cell.textContent = CHARSET[step];
            step++;
            return;
          }

          clearInterval(id);
          cell.textContent = finalChar;
          cell.classList.remove("flipping");
          cell.classList.add("settled");

          later(function () {
            cell.classList.remove("settled");
          }, 140);
        }, 26);
      }, delay);
    });
  }

  function render(animate) {
    var rows = ensure();
    if (!rows) return;

    clearSpin();

    var list = empty ? [{ time: "", title: "NO SCHEDULE EVENTS" }] : items;
    var n = Math.min(capacity(), list.length);
    var html = "";

    for (var i = 0; i < n; i++) {
      html += rowHtml(list[(offset + i) % list.length]);
    }

    rows.innerHTML = html;

    if (animate !== false) {
      requestAnimationFrame(function () {
        animateBoard(rows);
      });
    }
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
        return {
          time: e.time || e.start || e.start_time || e.date || "",
          title: e.text || e.title || e.summary || "Untitled"
        };
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }

  if (window.ResizeObserver) {
    var box = document.getElementById("agendaList");
    if (box) new ResizeObserver(function () { render(false); }).observe(box);
  }
})();
