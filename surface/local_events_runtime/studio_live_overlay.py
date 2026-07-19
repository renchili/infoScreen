from __future__ import annotations

# Injected into the operator-controlled Chromium page. The toolbar lives in a
# shadow root so official-site CSS cannot distort it, while all selections are
# made against the real page DOM rather than a screenshot or iframe.
OVERLAY_JS = r"""
(args) => {
  document.getElementById("__infoscreen_studio")?.remove();
  const host = document.createElement("div");
  host.id = "__infoscreen_studio";
  host.style.cssText = "all:initial;position:fixed;top:8px;right:8px;z-index:2147483647;font:13px system-ui;color:#e8eee9";
  const root = host.attachShadow({mode:"open"});
  const modes = [
    ["browse","BROWSE"],
    ["card","LIST CARD"],
    ["exclude","EXCLUDE"],
    ["url","DETAIL LINK"],
    ["title","TITLE"],
    ["when","WHEN"],
    ["where","WHERE"],
    ["summary","SUMMARY"],
    ["image","IMAGE"],
    ["action_click","RECORD CLICK"],
    ["action_repeat","REPEAT CLICK"],
    ["action_select","RECORD SELECT"],
  ];
  root.innerHTML = `<style>
    .p{width:390px;background:#09100c;border:1px solid #66736b;box-shadow:0 10px 34px #0009}
    .h{padding:9px;border-bottom:1px solid #344039;color:#8cff9b;font-weight:700}
    .b{padding:9px}.g{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
    .adjust,.action-row{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:6px}
    button,input,label{font:12px system-ui}
    button{min-height:32px;background:#101813;color:#e8eee9;border:1px solid #3d4a42;cursor:pointer}
    button.on{border-color:#8cff9b;color:#8cff9b}.wide{width:100%;margin-top:6px;color:#ffe08a}
    .settings{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-top:6px;align-items:end}
    .settings label{display:grid;gap:3px;color:#aab5ae;font-size:10px}.settings input{min-width:0;background:#050806;color:#e8eee9;border:1px solid #3d4a42;padding:5px}
    .optional{display:flex!important;align-items:center;gap:5px}.optional input{width:auto}
    .s{margin-top:7px;padding:7px;background:#050806;border:1px solid #2b352f;font:11px monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:170px;overflow:auto}
    .x{float:right;color:#ff9a9a}.r{margin-top:4px;color:#ffe08a;font-size:11px}
  </style><div class="p"><div class="h">INFOSCREEN LIVE STUDIO <button class="x">×</button>
  <div class="r" data-role></div></div>
  <div class="b"><div class="g">
    ${modes.map(([value,label])=>`<button data-m="${value}">${label}</button>`).join("")}
  </div>
  <div class="adjust"><button data-a="narrower">NARROWER ELEMENT</button><button data-a="wider">WIDER ELEMENT</button></div>
  <div class="settings">
    <label>WAIT MS<input data-wait type="number" min="0" max="15000" value="700"></label>
    <label>REPEAT MAX<input data-rounds type="number" min="1" max="50" value="20"></label>
    <label class="optional"><input data-optional type="checkbox">OPTIONAL</label>
  </div>
  <div class="action-row"><button data-a="scroll">RECORD SCROLL BOTTOM</button><button data-a="wait">RECORD WAIT</button></div>
  <button class="wide" data-a="clear-actions">CLEAR ACTIONS FOR THIS PAGE ROLE</button>
  <button class="wide" data-a="capture">SAVE CURRENT LISTING STATE</button>
  <button class="wide" data-a="clear">CLEAR ENTIRE DRAFT</button>
  <div class="s">Browse normally. Choose a mode only when selecting.</div></div></div>`;
  document.documentElement.appendChild(host);

  const status = root.querySelector(".s");
  const roleLabel = root.querySelector("[data-role]");
  const waitInput = root.querySelector("[data-wait]");
  const roundsInput = root.querySelector("[data-rounds]");
  const optionalInput = root.querySelector("[data-optional]");
  let mode = "browse";
  let outlined = null;
  let candidatePath = [];
  let candidateIndex = -1;

  const send = payload => window[args.binding](payload);
  const configured = new URL(args.listing_url, location.href);
  const currentRole = () => {
    const current = new URL(location.href);
    return current.hostname.toLowerCase() === configured.hostname.toLowerCase()
      && current.pathname.replace(/\/$/,"") === configured.pathname.replace(/\/$/,"")
      ? "listing"
      : "detail";
  };
  const updateRole = () => {
    roleLabel.textContent = currentRole() === "listing" ? "LISTING PAGE" : "DETAIL PAGE";
  };
  updateRole();
  const roleTimer = window.setInterval(updateRole, 500);

  const actionSettings = () => ({
    wait_ms: Math.max(0, Math.min(15000, Number(waitInput.value || 0))),
    max_rounds: Math.max(1, Math.min(50, Number(roundsInput.value || 1))),
    optional: Boolean(optionalInput.checked),
  });
  const esc = value => window.CSS?.escape
    ? CSS.escape(value)
    : String(value).replace(/[^a-zA-Z0-9_-]/g, ch => "\\" + ch);
  const stable = value => /^[a-zA-Z_][a-zA-Z0-9_-]{0,80}$/.test(String(value || ""));
  const visible = element => {
    if (!(element instanceof Element)) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) !== 0
      && rect.width >= 4 && rect.height >= 4;
  };
  const clearOutline = () => {
    if (outlined) {
      outlined.style.outline = "";
      outlined.style.outlineOffset = "";
    }
    outlined = null;
  };
  const outline = (element, color) => {
    clearOutline();
    if (element) {
      outlined = element;
      element.style.outline = `4px solid ${color}`;
      element.style.outlineOffset = "-2px";
    }
  };

  const selectorPart = (element, nth = false) => {
    let output = element.tagName.toLowerCase();
    for (const attribute of ["data-testid","data-test","data-component","data-module"]) {
      const value = element.getAttribute(attribute);
      if (value && /^[a-zA-Z0-9_.:-]{1,120}$/.test(value)) {
        return `${output}[${attribute}="${value}"]`;
      }
    }
    const classes = [...element.classList]
      .filter(stable)
      .filter(name => !/^(active|selected|open|hover|focus|loaded|visible|hidden)$/i.test(name))
      .slice(0,3);
    if (classes.length) output += "." + classes.map(esc).join(".");
    if (nth && element.parentElement) {
      const siblings = [...element.parentElement.children].filter(item => item.tagName === element.tagName);
      if (siblings.length > 1) output += `:nth-of-type(${siblings.indexOf(element)+1})`;
    }
    return output;
  };

  const uniqueSelector = element => {
    if (stable(element.id)) return "#" + esc(element.id);
    const parts = [];
    let current = element;
    for (let depth=0; current && current !== document.body && depth<8; depth++, current=current.parentElement) {
      parts.unshift(selectorPart(current, true));
      const candidate = parts.join(" > ");
      try { if (document.querySelectorAll(candidate).length === 1) return candidate; } catch {}
    }
    return parts.join(" > ");
  };

  const relativeSelector = (element, card) => {
    if (!card || !card.contains(element) || card === element) return "";
    const parts = [];
    let current = element;
    for (let depth=0; current && current !== card && depth<10; depth++, current=current.parentElement) {
      parts.unshift(selectorPart(current, true));
      const candidate = parts.join(" > ");
      try {
        if (card.querySelectorAll(candidate).length === 1) return candidate;
      } catch {}
    }
    return current === card ? parts.join(" > ") : "";
  };

  const repeatedSelector = element => {
    const selector = selectorPart(element, false);
    try { return {selector, count: document.querySelectorAll(selector).length}; }
    catch { return {selector:"", count:0}; }
  };

  const detailLinks = element => [...element.querySelectorAll("a[href]")].filter(anchor => {
    try {
      const url = new URL(anchor.getAttribute("href"), location.href);
      return /^https?:$/.test(url.protocol)
        && url.hostname.toLowerCase() === location.hostname.toLowerCase()
        && url.pathname.replace(/\/$/,"") !== location.pathname.replace(/\/$/,"");
    } catch { return false; }
  });

  const cardScore = (element, count) => {
    if (!visible(element) || count < 2 || count > 250) return -10000;
    const rect = element.getBoundingClientRect();
    const text = String(element.innerText || element.textContent || "").replace(/\s+/g," ").trim();
    if (rect.width < 100 || rect.height < 45 || text.length < 8 || text.length > 5000) return -10000;
    if (["HTML","BODY","MAIN","HEADER","FOOTER","NAV","FORM"].includes(element.tagName)) return -10000;
    if (rect.width > Math.max(innerWidth * .98, 1600) && rect.height > innerHeight * 1.5) return -10000;
    const attributes = [element.id, element.className, element.getAttribute("role"), element.getAttribute("data-component")].join(" ");
    const links = detailLinks(element).length;
    let score = 0;
    if (["ARTICLE","LI"].includes(element.tagName)) score += 55;
    if (/\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attributes)) score += 70;
    if (element.querySelector("h1,h2,h3,h4")) score += 22;
    if (links === 1) score += 55;
    if (links > 1) score -= Math.min(100, (links - 1) * 30);
    if (count <= 80) score += 20;
    if (rect.height > 1200 || text.length > 2500) score -= 60;
    score -= Math.min(45, Math.log10(Math.max(1, rect.width * rect.height)) * 4);
    return score;
  };

  const buildCardPath = target => {
    const candidates = [];
    let current = target;
    for (let depth=0; current && current !== document.body && depth<12; depth++, current=current.parentElement) {
      const repeated = repeatedSelector(current);
      const score = cardScore(current, repeated.count);
      if (score > -10000) candidates.push({element:current, ...repeated, score});
    }
    candidates.sort((a,b) => {
      const aRect = a.element.getBoundingClientRect();
      const bRect = b.element.getBoundingClientRect();
      return aRect.width * aRect.height - bRect.width * bRect.height;
    });
    return candidates;
  };

  const showCandidate = () => {
    const candidate = candidatePath[candidateIndex];
    if (!candidate) {
      clearOutline();
      status.textContent = "No repeated semantic card around this element. Move to the card body or prepare the page first.";
      return;
    }
    outline(candidate.element, mode === "exclude" ? "#ff9a9a" : "#8cecff");
    status.textContent = `${mode.toUpperCase()} candidate ${candidateIndex+1}/${candidatePath.length}\n${candidate.selector}\nMatches ${candidate.count} elements`;
  };

  const chooseBestCard = target => {
    candidatePath = buildCardPath(target);
    if (!candidatePath.length) {
      candidateIndex = -1;
      showCandidate();
      return null;
    }
    let best = 0;
    for (let index=1; index<candidatePath.length; index++) {
      if (candidatePath[index].score > candidatePath[best].score) best = index;
    }
    candidateIndex = best;
    showCandidate();
    return candidatePath[candidateIndex];
  };

  const selectedCard = element => {
    const remembered = window.__infoscreenCardSelector || "";
    if (remembered) {
      try {
        const owner = element.closest(remembered);
        if (owner) return owner;
      } catch {}
    }
    return null;
  };

  const setMode = value => {
    mode = value;
    candidatePath = [];
    candidateIndex = -1;
    root.querySelectorAll("[data-m]").forEach(button => button.classList.toggle("on", button.dataset.m === value));
    if (value === "browse") clearOutline();
    status.textContent = value === "browse"
      ? "Browse, scroll, filter, paginate or open details normally."
      : value === "action_select"
        ? "Choose the value normally first, then click RECORD SELECT and select the <select> element."
        : `Move over the real page and select ${value.toUpperCase()}.`;
  };

  const saveImmediateAction = async modeName => {
    try {
      const result = await send({
        action:"select",
        mode:modeName,
        page_role:currentRole(),
        selector:"",
        ...actionSettings(),
      });
      status.textContent = result.message;
    } catch (error) {
      status.textContent = "FAILED: " + error;
    }
  };

  root.querySelectorAll("[data-m]").forEach(button => button.onclick = () => setMode(button.dataset.m));
  root.querySelector(".x").onclick = () => {
    window.clearInterval(roleTimer);
    clearOutline();
    host.remove();
  };
  root.querySelector("[data-a='narrower']").onclick = () => {
    if (!candidatePath.length) return;
    candidateIndex = Math.max(0, candidateIndex - 1);
    showCandidate();
  };
  root.querySelector("[data-a='wider']").onclick = () => {
    if (!candidatePath.length) return;
    candidateIndex = Math.min(candidatePath.length - 1, candidateIndex + 1);
    showCandidate();
  };
  root.querySelector("[data-a='scroll']").onclick = () => saveImmediateAction("action_scroll");
  root.querySelector("[data-a='wait']").onclick = () => saveImmediateAction("action_wait");
  root.querySelector("[data-a='clear-actions']").onclick = () => saveImmediateAction("action_clear");
  root.querySelector("[data-a='clear']").onclick = async () => {
    if (confirm("Clear the current draft?")) status.textContent = (await send({action:"clear_draft"})).message;
  };
  root.querySelector("[data-a='capture']").onclick = async () => {
    try {
      status.textContent = "Opening and validating several real detail pages...";
      status.textContent = (await send({action:"capture_listing"})).message;
    } catch (error) {
      status.textContent = "FAILED: " + error;
    }
  };

  document.addEventListener("mousemove", event => {
    if (mode === "browse" || host.contains(event.target) || !(event.target instanceof Element)) return;
    const target = event.target;
    if (mode === "card" || mode === "exclude") {
      chooseBestCard(target);
      return;
    }
    let outlinedTarget = target;
    if (mode === "action_select") outlinedTarget = target.closest("select") || target;
    outline(outlinedTarget, mode.startsWith("action_") ? "#ffe08a" : "#8cecff");
    status.textContent = `${mode.toUpperCase()} target\n${uniqueSelector(outlinedTarget)}`;
  }, true);

  document.addEventListener("click", async event => {
    if (mode === "browse" || host.contains(event.target) || !(event.target instanceof Element)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      let element = event.target;
      let selector = "";
      let attribute = null;
      let matchedCount = 1;
      let value = null;
      const role = currentRole();
      const actionMode = mode.startsWith("action_");

      if (mode === "card" || mode === "exclude") {
        const candidate = candidatePath[candidateIndex] || chooseBestCard(element);
        if (!candidate) throw new Error("No repeated activity-card ancestor selected");
        element = candidate.element;
        selector = candidate.selector;
        matchedCount = candidate.count;
      } else if (actionMode) {
        if (mode === "action_select") {
          element = element.closest("select");
          if (!element) throw new Error("RECORD SELECT requires a native select element");
          value = element.value;
        }
        selector = uniqueSelector(element);
      } else if (role === "listing") {
        const card = selectedCard(element);
        if (!card) throw new Error("Select LIST CARD first, then select a field inside one matched card");
        if (mode === "url") {
          element = element.closest("a[href]");
          if (!element || !card.contains(element)) throw new Error("DETAIL LINK must be an anchor inside the selected card");
          attribute = "href";
        }
        if (mode === "image") {
          element = element.closest("img");
          if (!element || !card.contains(element)) throw new Error("IMAGE must be an img inside the selected card");
          attribute = element.hasAttribute("src") ? "src" : element.hasAttribute("data-src") ? "data-src" : "data-lazy-src";
        }
        selector = relativeSelector(element, card);
        if (!selector) throw new Error("Field must be inside the selected card");
      } else {
        if (mode === "url") throw new Error("DETAIL LINK belongs on the listing page");
        if (mode === "image") {
          element = element.closest("img");
          if (!element) throw new Error("IMAGE must be an img");
          attribute = element.hasAttribute("src") ? "src" : element.hasAttribute("data-src") ? "data-src" : "data-lazy-src";
        }
        selector = uniqueSelector(element);
      }

      const selectedMode = mode;
      const result = await send({
        action:"select",
        mode:selectedMode,
        page_role:role,
        selector,
        attribute,
        matched_count:matchedCount,
        value,
        page_url:location.href,
        ...actionSettings(),
      });
      if (selectedMode === "card") window.__infoscreenCardSelector = result.card_selector || selector;
      status.textContent = result.message;
      setMode("browse");

      if (selectedMode === "action_click" || selectedMode === "action_repeat") {
        window.setTimeout(() => {
          try { element.click(); } catch {}
        }, 50);
      }
    } catch (error) {
      status.textContent = "FAILED: " + error;
    }
  }, true);

  setMode("browse");
}
"""

__all__ = ["OVERLAY_JS"]
