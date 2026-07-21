"use strict";

(() => {
  const READY = "infoscreen-local-event-feedback-extension-ready";
  const PING = "infoscreen-local-event-feedback-extension-ping";
  const START = "infoscreen-local-event-feedback-start";
  const STARTED = "infoscreen-local-event-feedback-started";
  const TOOLBAR_ID = "__infoscreen_remote_event_feedback";

  function sendRuntime(message) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response || {});
        }
      });
    });
  }

  function announceReady() {
    window.postMessage({ type: READY, version: chrome.runtime.getManifest().version }, "*");
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window || !event.data || typeof event.data !== "object") return;
    if (event.data.type === PING) {
      announceReady();
      return;
    }
    if (event.data.type !== START) return;

    try {
      const response = await sendRuntime({
        type: "startFeedback",
        session: event.data.session,
      });
      window.postMessage({
        type: STARTED,
        ok: Boolean(response.ok),
        error: response.error || "",
      }, "*");
    } catch (error) {
      window.postMessage({
        type: STARTED,
        ok: false,
        error: String(error.message || error),
      }, "*");
    }
  });

  announceReady();

  function hostAllowed(listingUrl) {
    try {
      const expected = new URL(listingUrl).hostname.toLowerCase().replace(/^www\./, "");
      const current = window.location.hostname.toLowerCase().replace(/^www\./, "");
      return current === expected
        || current.endsWith(`.${expected}`)
        || expected.endsWith(`.${current}`);
    } catch {
      return false;
    }
  }

  function injectToolbar(session) {
    if (document.getElementById(TOOLBAR_ID) || !hostAllowed(session.listing_url)) return;

    const host = document.createElement("div");
    host.id = TOOLBAR_ID;
    host.style.cssText = "all:initial;position:fixed;top:10px;right:10px;z-index:2147483647;font:13px system-ui;color:#eef7f0";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      .panel{width:340px;background:#0c1210;border:1px solid #536158;box-shadow:0 12px 36px #0009}
      .head{padding:9px 10px;border-bottom:1px solid #354039;color:#9cffaa;font-weight:700}
      .body{padding:9px}.row{display:grid;grid-template-columns:1fr 1fr;gap:6px}
      button{font:12px system-ui;min-height:34px;background:#142019;color:#eef7f0;border:1px solid #536158;cursor:pointer}
      button.active{border-color:#9cffaa;color:#9cffaa}.submit{width:100%;margin-top:6px;color:#ffe18a}
      .status{margin-top:7px;padding:7px;background:#050806;border:1px solid #2e3832;white-space:pre-wrap;overflow-wrap:anywhere;max-height:160px;overflow:auto;font:11px monospace}
    </style>
    <div class="panel"><div class="head">INFOSCREEN · EVENT FEEDBACK</div><div class="body">
      <div class="row"><button data-action="browse" class="active">BROWSE</button><button data-action="mark">POINT TO EVENT</button></div>
      <div class="row" style="margin-top:6px"><button data-action="smaller">SMALLER</button><button data-action="larger">LARGER</button></div>
      <button data-action="submit" class="submit">SUBMIT THIS POSITION</button>
      <div class="status">Browse normally. Click POINT TO EVENT only when you want to report an activity location.</div>
    </div></div>`;
    document.documentElement.appendChild(host);

    const status = root.querySelector(".status");
    const browseButton = root.querySelector("[data-action='browse']");
    const markButton = root.querySelector("[data-action='mark']");
    let marking = false;
    let candidates = [];
    let candidateIndex = -1;
    let outlined = null;

    const stable = (value) => /^[A-Za-z_][A-Za-z0-9_-]{0,80}$/.test(String(value || ""));
    const esc = (value) => window.CSS && CSS.escape
      ? CSS.escape(value)
      : String(value).replace(/[^A-Za-z0-9_-]/g, (char) => `\\${char}`);
    const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();

    const visible = (element) => {
      if (!(element instanceof Element)) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none"
        && style.visibility !== "hidden"
        && Number(style.opacity || 1) !== 0
        && rect.width >= 8
        && rect.height >= 8;
    };

    const part = (element) => {
      if (stable(element.id)) return `#${esc(element.id)}`;
      let value = element.tagName.toLowerCase();
      for (const name of ["data-testid", "data-test", "data-component", "data-module"]) {
        const attribute = element.getAttribute(name);
        if (attribute && /^[A-Za-z0-9_.:-]{1,120}$/.test(attribute)) {
          return `${value}[${name}="${attribute}"]`;
        }
      }
      const classes = [...element.classList]
        .filter(stable)
        .filter((name) => !/^(active|selected|open|hover|focus|visible|hidden)$/i.test(name))
        .slice(0, 3);
      if (classes.length) value += `.${classes.map(esc).join(".")}`;
      return value;
    };

    const selectorFor = (element) => {
      if (stable(element.id)) return `#${esc(element.id)}`;
      const pieces = [];
      let current = element;
      for (let depth = 0; current && current !== document.body && depth < 8; depth += 1, current = current.parentElement) {
        pieces.unshift(part(current));
        const selector = pieces.join(" > ");
        try {
          const count = document.querySelectorAll(selector).length;
          if (count > 0 && count <= 100) return selector;
        } catch {}
      }
      return pieces.join(" > ");
    };

    const semanticScore = (element) => {
      if (!visible(element)) return -10000;
      const rect = element.getBoundingClientRect();
      const value = clean(element.innerText || element.textContent || "");
      if (value.length < 4 || value.length > 5000 || rect.width < 60 || rect.height < 24) return -10000;
      if (["HTML", "BODY", "MAIN", "HEADER", "FOOTER", "NAV", "FORM"].includes(element.tagName)) return -10000;
      const attrs = clean([element.id, element.className, element.getAttribute("role"), element.getAttribute("data-component")].join(" "));
      let score = 0;
      if (["ARTICLE", "LI"].includes(element.tagName)) score += 50;
      if (/\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attrs)) score += 65;
      if (element.querySelector("h1,h2,h3,h4")) score += 20;
      if (element.querySelector("a[href]")) score += 25;
      if (rect.height > 1200 || value.length > 2500) score -= 60;
      return score;
    };

    const buildCandidates = (target) => {
      const rows = [];
      let current = target;
      for (let depth = 0; current && current !== document.body && depth < 12; depth += 1, current = current.parentElement) {
        const score = semanticScore(current);
        if (score > -10000) rows.push({ element: current, score });
      }
      rows.sort((left, right) => {
        const lr = left.element.getBoundingClientRect();
        const rr = right.element.getBoundingClientRect();
        return lr.width * lr.height - rr.width * rr.height;
      });
      return rows;
    };

    const clearOutline = () => {
      if (outlined) {
        outlined.style.outline = "";
        outlined.style.outlineOffset = "";
      }
      outlined = null;
    };

    const showCandidate = () => {
      clearOutline();
      const candidate = candidates[candidateIndex];
      if (!candidate) {
        status.textContent = "Move over an activity card, row, tile, or link and click it.";
        return;
      }
      outlined = candidate.element;
      outlined.style.outline = "4px solid #9cffaa";
      outlined.style.outlineOffset = "-2px";
      const selector = selectorFor(outlined);
      let count = 1;
      try { count = document.querySelectorAll(selector).length; } catch {}
      status.textContent = `Selected ${candidateIndex + 1}/${candidates.length}\n${selector}\nMatches ${count} elements`;
    };

    const setMode = (value) => {
      marking = value === "mark";
      browseButton.classList.toggle("active", !marking);
      markButton.classList.toggle("active", marking);
      if (!marking) {
        candidates = [];
        candidateIndex = -1;
        clearOutline();
        status.textContent = "Browse normally. Click POINT TO EVENT only when you want to report an activity location.";
      } else {
        status.textContent = "Click the activity element you want to report. Normal page clicks are paused only for that selection.";
      }
    };

    browseButton.onclick = () => setMode("browse");
    markButton.onclick = () => setMode("mark");
    root.querySelector("[data-action='smaller']").onclick = () => {
      if (!candidates.length) return;
      candidateIndex = Math.max(0, candidateIndex - 1);
      showCandidate();
    };
    root.querySelector("[data-action='larger']").onclick = () => {
      if (!candidates.length) return;
      candidateIndex = Math.min(candidates.length - 1, candidateIndex + 1);
      showCandidate();
    };

    root.querySelector("[data-action='submit']").onclick = async () => {
      const candidate = candidates[candidateIndex];
      if (!candidate) {
        status.textContent = "Select an activity element first.";
        return;
      }
      const element = candidate.element;
      const selector = selectorFor(element);
      const matches = [...document.querySelectorAll(selector)];
      const rect = element.getBoundingClientRect();
      const link = element.matches("a[href]") ? element : element.querySelector("a[href]");
      status.textContent = "Saving feedback to InfoScreen...";
      try {
        const response = await sendRuntime({
          type: "submitFeedback",
          payload: {
            page_url: window.location.href,
            selector,
            selector_index: Math.max(0, matches.indexOf(element)),
            selector_match_count: Math.max(1, matches.length),
            document_position: {
              x: Math.round(rect.x + scrollX),
              y: Math.round(rect.y + scrollY),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
            },
            text: clean(element.innerText || element.textContent || "").slice(0, 3000),
            href: link ? new URL(link.getAttribute("href"), window.location.href).href : "",
          },
        });
        if (!response.ok) throw new Error(response.error || "Feedback save failed");
        status.textContent = "Feedback saved to InfoScreen.";
        window.setTimeout(() => setMode("browse"), 700);
      } catch (error) {
        status.textContent = `FAILED: ${String(error.message || error)}`;
      }
    };

    document.addEventListener("mousemove", (event) => {
      if (!marking || host.contains(event.target) || !(event.target instanceof Element)) return;
      candidates = buildCandidates(event.target);
      if (!candidates.length) return;
      let best = 0;
      for (let index = 1; index < candidates.length; index += 1) {
        if (candidates[index].score > candidates[best].score) best = index;
      }
      candidateIndex = best;
      showCandidate();
    }, true);

    document.addEventListener("click", (event) => {
      if (!marking || host.contains(event.target) || !(event.target instanceof Element)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      candidates = buildCandidates(event.target);
      if (!candidates.length) {
        status.textContent = "No usable activity element found around that click.";
        return;
      }
      let best = 0;
      for (let index = 1; index < candidates.length; index += 1) {
        if (candidates[index].score > candidates[best].score) best = index;
      }
      candidateIndex = best;
      showCandidate();
    }, true);

    setMode("browse");
  }

  sendRuntime({ type: "getFeedbackSession" })
    .then((response) => {
      if (response.ok && response.session) injectToolbar(response.session);
    })
    .catch(() => {});
})();
