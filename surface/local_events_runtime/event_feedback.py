from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .browser import find_browser_executable
from .event_review import DEFAULT_CONFIG_PATH, DEFAULT_REVIEW_ROOT, EventReviewStore, canonical_url

OVERLAY_JS = r"""
(args) => {
  document.getElementById("__infoscreen_event_feedback")?.remove();

  const host = document.createElement("div");
  host.id = "__infoscreen_event_feedback";
  host.style.cssText = "all:initial;position:fixed;top:10px;right:10px;z-index:2147483647;font:13px system-ui;color:#eef7f0";
  const root = host.attachShadow({mode: "open"});
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

  const stable = value => /^[A-Za-z_][A-Za-z0-9_-]{0,80}$/.test(String(value || ""));
  const esc = value => window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/[^A-Za-z0-9_-]/g, char => "\\" + char);
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();

  const visible = element => {
    if (!(element instanceof Element)) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) !== 0 && rect.width >= 8 && rect.height >= 8;
  };

  const part = element => {
    if (stable(element.id)) return "#" + esc(element.id);
    let value = element.tagName.toLowerCase();
    for (const name of ["data-testid", "data-test", "data-component", "data-module"]) {
      const attribute = element.getAttribute(name);
      if (attribute && /^[A-Za-z0-9_.:-]{1,120}$/.test(attribute)) return `${value}[${name}="${attribute}"]`;
    }
    const classes = [...element.classList].filter(stable).filter(name => !/^(active|selected|open|hover|focus|visible|hidden)$/i.test(name)).slice(0, 3);
    if (classes.length) value += "." + classes.map(esc).join(".");
    return value;
  };

  const selectorFor = element => {
    if (stable(element.id)) return "#" + esc(element.id);
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

  const semanticScore = element => {
    if (!visible(element)) return -10000;
    const rect = element.getBoundingClientRect();
    const text = clean(element.innerText || element.textContent || "");
    if (text.length < 4 || text.length > 5000 || rect.width < 60 || rect.height < 24) return -10000;
    if (["HTML", "BODY", "MAIN", "HEADER", "FOOTER", "NAV", "FORM"].includes(element.tagName)) return -10000;
    const attrs = clean([element.id, element.className, element.getAttribute("role"), element.getAttribute("data-component")].join(" "));
    let score = 0;
    if (["ARTICLE", "LI"].includes(element.tagName)) score += 50;
    if (/\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attrs)) score += 65;
    if (element.querySelector("h1,h2,h3,h4")) score += 20;
    if (element.querySelector("a[href]")) score += 25;
    if (rect.height > 1200 || text.length > 2500) score -= 60;
    return score;
  };

  const buildCandidates = target => {
    const rows = [];
    let current = target;
    for (let depth = 0; current && current !== document.body && depth < 12; depth += 1, current = current.parentElement) {
      const score = semanticScore(current);
      if (score > -10000) rows.push({element: current, score});
    }
    rows.sort((a, b) => {
      const ar = a.element.getBoundingClientRect();
      const br = b.element.getBoundingClientRect();
      return ar.width * ar.height - br.width * br.height;
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

  const setMode = value => {
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
    try {
      const response = await window[args.binding]({
        source_id: args.source_id,
        listing_url: args.listing_url,
        page_url: location.href,
        selector,
        selector_index: Math.max(0, matches.indexOf(element)),
        selector_match_count: Math.max(1, matches.length),
        document_position: {
          x: Math.round(rect.x + scrollX),
          y: Math.round(rect.y + scrollY),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        },
        text: clean(element.innerText || element.textContent || "").slice(0, 3000),
        href: link ? new URL(link.getAttribute("href"), location.href).href : ""
      });
      status.textContent = response.message || "Feedback saved.";
      setTimeout(() => setMode("browse"), 700);
    } catch (error) {
      status.textContent = "FAILED: " + error;
    }
  };

  document.addEventListener("mousemove", event => {
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

  document.addEventListener("click", event => {
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
"""


def _host_allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in source.get("allowed_domains") or []
        )
    )


def session_path(root: Path, source_id: str, listing_url: str) -> Path:
    import hashlib

    digest = hashlib.sha256(canonical_url(listing_url).encode("utf-8")).hexdigest()[:16]
    path = root / "browser_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{source_id}-{digest}.json"


def write_session(root: Path, source_id: str, listing_url: str, **values: Any) -> dict[str, Any]:
    path = session_path(root, source_id, listing_url)
    current: dict[str, Any] = {}
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    payload = {
        "source_id": source_id,
        "listing_url": canonical_url(listing_url),
        **current,
        **values,
        "updated_at": time.time(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return payload


def start_feedback_browser(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_REVIEW_ROOT,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    review_root = Path(root).expanduser().resolve()
    store = EventReviewStore(review_root, config_path)
    source = store.source(source_id)
    canonical_listing = canonical_url(listing_url)
    if not _host_allowed(canonical_listing, source):
        raise ValueError("listing URL is outside the source allow-list")

    worker = Path(__file__).resolve().parents[1] / "jobs" / "local_event_feedback.py"
    environment = os.environ.copy()
    environment["INFOSCREEN_ENV_DIR"] = str(review_root.parent)
    process = subprocess.Popen(
        [sys.executable, str(worker), source_id, canonical_listing],
        cwd=str(worker.parents[1]),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=environment,
    )
    return write_session(
        review_root,
        source_id,
        canonical_listing,
        pid=process.pid,
        status="starting",
        page_url=canonical_listing,
    )


def run_feedback_browser(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_REVIEW_ROOT,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> int:
    review_root = Path(root).expanduser().resolve()
    store = EventReviewStore(review_root, config_path)
    source = store.source(source_id)
    canonical_listing = canonical_url(listing_url)
    if not _host_allowed(canonical_listing, source):
        raise ValueError("listing URL is outside the source allow-list")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        write_session(review_root, source_id, canonical_listing, status="failed", error=f"missing_playwright:{exc}")
        return 2

    executable = find_browser_executable()
    if not executable:
        write_session(review_root, source_id, canonical_listing, status="failed", error="missing_system_chromium")
        return 3

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(review_root / "browser_profiles" / source_id),
            headless=False,
            executable_path=executable,
            viewport=None,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--start-maximized"],
        )

        def save_feedback(binding: Any, payload: Any) -> dict[str, Any]:
            row = store.append_feedback(dict(payload or {}))
            return {"ok": True, "message": f"Feedback saved: {row.selector}"}

        context.expose_binding("__infoscreenSaveEventFeedback", save_feedback)

        def install(page: Any) -> None:
            if not _host_allowed(str(page.url), source):
                return
            page.evaluate(
                OVERLAY_JS,
                {
                    "binding": "__infoscreenSaveEventFeedback",
                    "source_id": source_id,
                    "listing_url": canonical_listing,
                },
            )
            write_session(
                review_root,
                source_id,
                canonical_listing,
                pid=os.getpid(),
                status="running",
                page_url=str(page.url),
            )

        def configure(page: Any) -> None:
            page.on("domcontentloaded", lambda: install(page))

        for page in context.pages:
            configure(page)
        context.on("page", configure)

        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(canonical_listing, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(canonical_listing, wait_until="commit", timeout=30000)
        page.wait_for_timeout(400)
        install(page)

        try:
            while context.pages:
                time.sleep(0.5)
        finally:
            write_session(review_root, source_id, canonical_listing, status="closed")
            context.close()
    return 0


__all__ = ["run_feedback_browser", "start_feedback_browser"]
