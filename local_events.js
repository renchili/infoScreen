(function () {
  "use strict";

  var CACHE_URL = "/local_event_search_results.json";
  var API_URL = "/api/local-events/search";
  var LOCATION_KEY = "infoscreen.local-event.location";
  var DEFAULT_LOCATION = "Punggol Singapore";

  function q(selector, root) {
    return (root || document).querySelector(selector);
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function clean(value, max) {
    var text = String(value == null ? "" : value)
      .replace(/\s+/g, " ")
      .trim();

    if (max && text.length > max) {
      return text.slice(0, max - 1).trim() + "…";
    }

    return text;
  }

  function panel() {
    var el = q("#localEventsPanel") || q(".local-event-static");

    if (!el) {
      el = document.createElement("section");
      el.id = "localEventsPanel";
      el.className = "local-event-static";
      (q(".left-panel") || q(".sidebar") || document.body).appendChild(el);
    }

    el.id = "localEventsPanel";
    el.className = "local-event-static";
    return el;
  }

  function normalizeEvents(data) {
    var rows = data && (data.results || data.items);
    if (!Array.isArray(rows)) return [];

    return rows
      .filter(function (item) {
        return item && item.type !== "source" && item.title && item.url;
      })
      .slice(0, 64)
      .map(function (item) {
        return {
          title: clean(item.title, 145),
          url: clean(item.url, 500),
          source: clean(item.source_name || item.host || item.source || "Official source", 52),
          date: clean(item.when || item.date || "Check official page", 72),
          venue: clean(item.where || item.venue || "", 96),
          summary: clean(item.summary || "", 220)
        };
      });
  }

  function normalizeSources(data) {
    var rows = data && data.sources;
    if (!Array.isArray(rows)) return [];

    return rows
      .filter(function (item) {
        return item && item.title && item.url;
      })
      .slice(0, 12)
      .map(function (item) {
        return {
          title: clean(item.title, 38),
          url: clean(item.url, 500)
        };
      });
  }

  function groupEvents(events) {
    var order = [];
    var groups = {};
    events.forEach(function (item) {
      var key = item.source || "Official source";
      if (!groups[key]) {
        groups[key] = [];
        order.push(key);
      }
      groups[key].push(item);
    });
    return order.map(function (key) {
      return { source: key, items: groups[key] };
    });
  }

  function eventCard(item) {
    return [
      '<article class="le2-card">',
      '<div class="le2-row">',
      '<span class="le2-source">', esc(item.source), '</span>',
      '<span class="le2-date">', esc(item.date), '</span>',
      '</div>',
      '<a class="le2-event-title" href="', esc(item.url),
      '" target="_blank" rel="noopener noreferrer">',
      esc(item.title),
      '</a>',
      item.venue
        ? '<div class="le2-venue">WHERE ' + esc(item.venue) + '</div>'
        : '',
      item.summary
        ? '<p class="le2-summary">' + esc(item.summary) + '</p>'
        : '',
      '</article>'
    ].join("");
  }

  function eventGroup(group) {
    return [
      '<section class="le2-group">',
      '<div class="le2-group-title">', esc(group.source),
      '<span>', esc(group.items.length + ' item' + (group.items.length === 1 ? '' : 's')), '</span>',
      '</div>',
      group.items.map(eventCard).join(""),
      '</section>'
    ].join("");
  }

  function sourceCard(item) {
    return [
      '<a class="le2-source-link" href="', esc(item.url),
      '" target="_blank" rel="noopener noreferrer">',
      esc(item.title),
      '</a>'
    ].join("");
  }

  function draw(data, status) {
    var el = panel();
    var location = clean(
      (data && data.location) ||
      localStorage.getItem(LOCATION_KEY) ||
      DEFAULT_LOCATION,
      80
    );

    var events = normalizeEvents(data);
    var sources = normalizeSources(data);
    var count = events.length;
    var groups = groupEvents(events);

    var eventHtml = events.length
      ? groups.map(eventGroup).join("")
      : '<div class="le2-empty">No confirmed event cards found yet. Use the official calendars below.</div>';

    var sourceHtml = sources.length
      ? '<div class="le2-official-title">OFFICIAL SOURCES</div>' +
        '<div class="le2-source-list">' +
        sources.map(sourceCard).join("") +
        '</div>'
      : "";

    el.innerHTML = [
      '<div class="le2-header">',
      '<div>',
      '<div class="le2-kicker">LOCAL EVENTS</div>',
      '<div class="le2-title">Nearby Picks</div>',
      '</div>',
      '<div class="le2-status">',
      esc(status || (count + ' event' + (count === 1 ? '' : 's') + ' / ' + groups.length + ' source' + (groups.length === 1 ? '' : 's'))),
      '</div>',
      '</div>',

      '<div class="le2-controls">',
      '<input id="le2Location" class="le2-input" value="', esc(location), '">',
      '<button id="le2Scan" class="le2-button" type="button">SCAN</button>',
      '</div>',

      '<div class="le2-list">', eventHtml, '</div>',
      sourceHtml
    ].join("");

    var input = q("#le2Location", el);
    var button = q("#le2Scan", el);

    button.addEventListener("click", function () {
      refresh(input.value);
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        refresh(input.value);
      }
    });
  }

  function load() {
    fetch(CACHE_URL + "?v=" + Date.now(), { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        draw(data);
      })
      .catch(function (error) {
        draw({ results: [], sources: [] }, "Cache unavailable: " + error.message);
      });
  }

  function refresh(location) {
    location = clean(location || DEFAULT_LOCATION, 80) || DEFAULT_LOCATION;
    localStorage.setItem(LOCATION_KEY, location);

    draw(
      { location: location, results: [], sources: [] },
      "Scanning official sources…"
    );

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ location: location })
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || ("HTTP " + response.status));
          }
          return data;
        });
      })
      .then(function (data) {
        draw(data);
      })
      .catch(function (error) {
        draw(
          { location: location, results: [], sources: [] },
          "Search failed: " + error.message
        );
      });
  }

  window.refreshLocalEvents = refresh;

  document.addEventListener("DOMContentLoaded", load);
})();
