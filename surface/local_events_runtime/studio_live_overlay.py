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
  const modes = ["browse","card","exclude","url","title","when","where","summary","image"];
  root.innerHTML = `<style>
    .p{width:360px;background:#09100c;border:1px solid #66736b;box-shadow:0 10px 34px #0009}
    .h{padding:9px;border-bottom:1px solid #344039;color:#8cff9b;font-weight:700}
    .b{padding:9px}.g{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
    .adjust{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:6px}
    button{font:12px system-ui;min-height:32px;background:#101813;color:#e8eee9;border:1px solid #3d4a42;cursor:pointer}
    button.on{border-color:#8cff9b;color:#8cff9b}.wide{width:100%;margin-top:6px;color:#ffe08a}
    .s{margin-top:7px;padding:7px;background:#050806;border:1px solid #2b352f;font:11px monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:150px;overflow:auto}
    .x{float:right;color:#ff9a9a}.r{margin-top:4px;color:#ffe08a;font-size:11px}
  </style><div class="p"><div class="h">INFOSCREEN LIVE STUDIO <button class="x">×</button>
  <div class="r">${args.role === "detail" ? "DETAIL PAGE" : "LISTING PAGE"}</div></div>
  <div class="b"><div class="g">
    ${modes.map(x=>`<button data-m="${x}">${x === "url" ? "DETAIL LINK" : x.toUpperCase()}</button>`).join("")}
  </div><div class="adjust"><button data-a="narrower">NARROWER ELEMENT</button><button data-a="wider">WIDER ELEMENT</button></div>
  <button class="wide" data-a="capture">SAVE CURRENT LISTING STATE</button>
  <button class="wide" data-a="clear">CLEAR DRAFT</button><div class="s">Browse normally. Choose a mode only when selecting.</div></div></div>`;
  document.documentElement.appendChild(host);

  const status = root.querySelector(".s");
  let mode = "browse";
  let outlined = null;
  let pointerTarget = null;
  let candidatePath = [];
  let candidateIndex = -1;

  const send = payload => window[args.binding](payload);
  const esc = value => window.CSS?.escape
    ? CSS.escape(value)
    : String(value).replace(/[^a-zA-Z0-9_-]/g, ch => "\\" + ch);
  const stable = value => /^[a-zA-Z_][a-zA-Z0-9_-]{0,80}$/.test(String(value || ""));
  const visible = el => {
    if (!(el instanceof Element)) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) !== 0
      && rect.width >= 4 && rect.height >= 4;
  };
  const clearOutline = () => {
    if (outlined) outlined.style.outline = "";
    outlined = null;
  };
  const outline = (el, color) => {
    clearOutline();
    if (el) {
      outlined = el;
      el.style.outline = `4px solid ${color}`;
      el.style.outlineOffset = "-2px";
    }
  };

  const selectorPart = (el, nth = false) => {
    let output = el.tagName.toLowerCase();
    for (const attribute of ["data-testid","data-test","data-component","data-module"]) {
      const value = el.getAttribute(attribute);
      if (value && /^[a-zA-Z0-9_.:-]{1,120}$/.test(value)) {
        return `${output}[${attribute}="${value}"]`;
      }
    }
    const classes = [...el.classList]
      .filter(stable)
      .filter(name => !/^(active|selected|open|hover|focus|loaded|visible|hidden)$/i.test(name))
      .slice(0,3);
    if (classes.length) output += "." + classes.map(esc).join(".");
    if (nth && el.parentElement) {
      const siblings = [...el.parentElement.children].filter(item => item.tagName === el.tagName);
      if (siblings.length > 1) output += `:nth-of-type(${siblings.indexOf(el)+1})`;
    }
    return output;
  };

  const uniqueSelector = el => {
    if (stable(el.id)) return "#" + esc(el.id);
    const parts = [];
    let current = el;
    for (let depth=0; current && current !== document.body && depth<8; depth++, current=current.parentElement) {
      parts.unshift(selectorPart(current, true));
      const candidate = parts.join(" > ");
      try { if (document.querySelectorAll(candidate).length === 1) return candidate; } catch {}
    }
    return parts.join(" > ");
  };

  const repeatedSelector = el => {
    const selector = selectorPart(el, false);
    try { return {selector, count: document.querySelectorAll(selector).length}; }
    catch { return {selector:"", count:0}; }
  };

  const detailLinks = el => [...el.querySelectorAll("a[href]")].filter(anchor => {
    try {
      const url = new URL(anchor.getAttribute("href"), location.href);
      return /^https?:$/.test(url.protocol) && url.hostname === location.hostname && url.pathname !== location.pathname;
    } catch { return false; }
  });

  const cardScore = (el, count) => {
    if (!visible(el) || count < 2 || count > 250) return -10000;
    const rect = el.getBoundingClientRect();
    const text = String(el.innerText || el.textContent || "").replace(/\s+/g," ").trim();
    if (rect.width < 100 || rect.height < 45 || text.length < 8 || text.length > 5000) return -10000;
    if (["HTML","BODY","MAIN","HEADER","FOOTER","NAV","FORM"].includes(el.tagName)) return -10000;
    if (rect.width > Math.max(innerWidth * .98, 1600) && rect.height > innerHeight * 1.5) return -10000;
    const attributes = [el.id, el.className, el.getAttribute("role"), el.getAttribute("data-component")].join(" ");
    const links = detailLinks(el).length;
    let score = 0;
    if (["ARTICLE","LI"].includes(el.tagName)) score += 55;
    if (/\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attributes)) score += 70;
    if (el.querySelector("h1,h2,h3,h4")) score += 22;
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
      const areaA = a.element.getBoundingClientRect().width * a.element.getBoundingClientRect().height;
      const areaB = b.element.getBoundingClientRect().width * b.element.getBoundingClientRect().height;
      return areaA - areaB;
    });
    return candidates;
  };

  const showCandidate = () => {
    const candidate = candidatePath[candidateIndex];
    if (!candidate) {
      clearOutline();
      status.textContent = "No repeated semantic card around this element. Move to the card body or edit the site filters first.";
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

  const selectedCard = el => {
    const remembered = window.__infoscreenCardSelector || "";
    if (remembered) {
      try {
        const owner = el.closest(remembered);
        if (owner) return owner;
      } catch {}
    }
    return null;
  };

  const relativeSelector = (el, card) => {
    if (!card || !card.contains(el) || card === el) return "";
    const parts = [];
    let current = el;
    for (let depth=0; current && current !== card && depth<10; depth++, current=current.parentElement) {
      parts.unshift(selectorPart(current, false));
    }
    return current === card ? parts.join(" > ") : "";
  };

  const setMode = value => {
    mode = value;
    candidatePath = [];
    candidateIndex = -1;
    root.querySelectorAll("[data-m]").forEach(button => button.classList.toggle("on", button.dataset.m === value));
    if (value === "browse") clearOutline();
    status.textContent = value === "browse"
      ? "Browse, scroll, filter, paginate or open details normally."
      : `Move over the real page and select ${value.toUpperCase()}.`;
  };

  root.querySelectorAll("[data-m]").forEach(button => button.onclick = () => setMode(button.dataset.m));
  root.querySelector(".x").onclick = () => { clearOutline(); host.remove(); };
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
    pointerTarget = event.target;
    if (mode === "card" || mode === "exclude") {
      chooseBestCard(pointerTarget);
    } else {
      outline(pointerTarget, "#8cecff");
      status.textContent = `${mode.toUpperCase()} target\n${uniqueSelector(pointerTarget)}`;
    }
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

      if (mode === "card" || mode === "exclude") {
        const candidate = candidatePath[candidateIndex] || chooseBestCard(element);
        if (!candidate) throw new Error("No repeated activity-card ancestor selected");
        element = candidate.element;
        selector = candidate.selector;
        matchedCount = candidate.count;
      } else if (args.role === "listing") {
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

      const result = await send({
        action:"select",
        mode,
        page_role:args.role,
        selector,
        attribute,
        matched_count:matchedCount,
        page_url:location.href,
      });
      if (mode === "card") window.__infoscreenCardSelector = result.card_selector || selector;
      status.textContent = result.message;
      setMode("browse");
    } catch (error) {
      status.textContent = "FAILED: " + error;
    }
  }, true);

  setMode("browse");
}
"""

__all__ = ["OVERLAY_JS"]
