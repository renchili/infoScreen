(function () {
  var api = "/api/local-events/search";
  var list = [];
  var page = 0;
  function el(id) { return document.getElementById(id); }
  function txt(v) { return String(v == null ? "" : v).replace(/\s+/g, " ").trim(); }
  function enc(v) { return txt(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function rows(data) { return Array.isArray(data) ? data : ((data && (data.results || data.items || data.events)) || []); }
  function val(row, keys) { for (var i = 0; i < keys.length; i++) { var v = txt(row && row[keys[i]]); if (v) return v; } return ""; }
  function okurl(v) { v = txt(v); return /^https?:\/\//i.test(v) ? v : ""; }
  function item(row, i) { return { title: val(row, ["title", "what_text", "name", "event", "summary"]), when: val(row, ["when", "when_text", "date", "date_text", "time", "time_text"]), where: val(row, ["where", "venue", "place", "where_text", "location"]), source: val(row, ["source_name", "host", "organizer", "source"]), summary: val(row, ["summary", "description", "desc", "why_text"]), link: okurl(val(row, ["url", "link", "href", "official_url"])), order: Number(row && (row.source_order == null ? i : row.source_order)) }; }
  function fact(k, v) { v = txt(v); return v ? '<div class="local-event-kv"><span>' + enc(k) + '</span><b>' + enc(v) + '</b></div>' : ""; }
  function drawEmpty(v) { var box = el("localEventList"); if (box) box.innerHTML = '<div class="local-event-empty">' + enc(v) + '</div>'; }
  function draw() { var box = el("localEventList"); if (!box) return; if (!list.length) return drawEmpty("NO RENDERABLE EVENTS"); if (page < 0) page = list.length - 1; if (page >= list.length) page = 0; var x = list[page]; var action = x.link ? '<a class="local-event-link" href="' + enc(x.link) + '">OPEN OFFICIAL LINK</a>' : '<span class="local-event-no-link">OFFICIAL SOURCE</span>'; box.innerHTML = '<div class="local-event-card active"><div class="local-event-source">' + enc(x.source || "Official source") + '</div><div class="local-event-title">' + enc(x.title || "Local event") + '</div><div class="local-event-facts">' + fact("WHEN", x.when) + fact("WHERE", x.where) + '</div><div class="local-event-desc"><div class="local-event-desc-text">' + enc(x.summary || "") + '</div></div><div class="local-event-actions">' + action + '</div></div>'; var c = el("localEventCounter"); if (c) c.textContent = (page + 1) + "/" + list.length; }
  function load() { fetch(api + "?_=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (data) { list = rows(data).map(item).filter(function (x) { return x.title; }).sort(function (a, b) { return (a.order || 0) - (b.order || 0); }); page = 0; draw(); }).catch(function () { drawEmpty("LOCAL EVENTS UNAVAILABLE"); }); }
  document.addEventListener("DOMContentLoaded", function () { var prev = el("localEventPrevButton"); var next = el("localEventNextButton"); if (prev) prev.onclick = function () { page--; draw(); }; if (next) next.onclick = function () { page++; draw(); }; load(); });
})();
