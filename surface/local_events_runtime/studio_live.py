from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .browser import find_browser_executable
from .extract import clean, label_dates
from .studio_capture import DOM_EVIDENCE_JS, write_snapshot
from .studio_evaluate import _write_test_run, rule_fingerprint, validate_detail_url
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRule,
    LocalEventStudioRuleStore,
    canonical_listing_url,
)

OVERLAY_JS = r"""
(args) => {
  document.getElementById("__infoscreen_studio")?.remove();
  const host = document.createElement("div");
  host.id = "__infoscreen_studio";
  host.style.cssText = "all:initial;position:fixed;top:8px;right:8px;z-index:2147483647;font:13px system-ui;color:#e8eee9";
  const root = host.attachShadow({mode:"open"});
  root.innerHTML = `<style>
    .p{width:330px;background:#09100c;border:1px solid #66736b;box-shadow:0 10px 34px #0009}
    .h{padding:9px;border-bottom:1px solid #344039;color:#8cff9b;font-weight:700}
    .b{padding:9px}.g{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
    button{font:12px system-ui;min-height:32px;background:#101813;color:#e8eee9;border:1px solid #3d4a42;cursor:pointer}
    button.on{border-color:#8cff9b;color:#8cff9b}.wide{width:100%;margin-top:6px;color:#ffe08a}
    .s{margin-top:7px;padding:7px;background:#050806;border:1px solid #2b352f;font:11px monospace;white-space:pre-wrap}
    .x{float:right;color:#ff9a9a}.r{margin-top:4px;color:#ffe08a;font-size:11px}
  </style><div class="p"><div class="h">INFOSCREEN LIVE STUDIO <button class="x">×</button>
  <div class="r">${args.role === "detail" ? "DETAIL PAGE" : "LISTING PAGE"}</div></div>
  <div class="b"><div class="g">
    ${["browse","card","exclude","url","title","when","where","summary","image"].map(x=>`<button data-m="${x}">${x.toUpperCase()}</button>`).join("")}
  </div><button class="wide" data-a="capture">SAVE CURRENT LISTING STATE</button>
  <button class="wide" data-a="clear">CLEAR DRAFT</button><div class="s">Browse normally. Choose a mode only when selecting.</div></div></div>`;
  document.documentElement.appendChild(host);

  const status = root.querySelector(".s");
  let mode = "browse", hover = null;
  const setMode = (value) => {
    mode = value;
    root.querySelectorAll("[data-m]").forEach(b => b.classList.toggle("on", b.dataset.m === value));
    if (value === "browse" && hover) { hover.style.outline = ""; hover = null; }
    status.textContent = value === "browse" ? "Browse, scroll, filter, paginate or open details normally." : `Select ${value.toUpperCase()} on the real page.`;
  };
  const esc = v => window.CSS?.escape ? CSS.escape(v) : String(v).replace(/[^a-zA-Z0-9_-]/g, c => "\\" + c);
  const stable = v => /^[a-zA-Z_][a-zA-Z0-9_-]{0,80}$/.test(String(v || ""));
  const part = (el, nth=false) => {
    let out = el.tagName.toLowerCase();
    for (const a of ["data-testid","data-test","data-component","data-module"]) {
      const v = el.getAttribute(a); if (v && /^[a-zA-Z0-9_.:-]{1,120}$/.test(v)) return `${out}[${a}="${v}"]`;
    }
    const cls = [...el.classList].filter(stable).filter(x=>!/^(active|selected|open|hover|focus|loaded|visible|hidden)$/i.test(x)).slice(0,3);
    if (cls.length) out += "." + cls.map(esc).join(".");
    if (nth && el.parentElement) {
      const sib = [...el.parentElement.children].filter(x=>x.tagName===el.tagName);
      if (sib.length > 1) out += `:nth-of-type(${sib.indexOf(el)+1})`;
    }
    return out;
  };
  const unique = el => {
    if (stable(el.id)) return "#" + esc(el.id);
    const p=[]; let cur=el;
    for (let i=0; cur && cur!==document.body && i<7; i++,cur=cur.parentElement) {
      p.unshift(part(cur,true)); const s=p.join(" > ");
      try { if (document.querySelectorAll(s).length===1) return s; } catch {}
    }
    return p.join(" > ");
  };
  const repeated = el => {
    let cur=el;
    for (let i=0;cur&&cur!==document.body&&i<7;i++,cur=cur.parentElement) {
      const s=part(cur,false); try { const n=document.querySelectorAll(s).length; if(n>=2&&n<=250)return {s,n}; } catch {}
    }
    return {s:part(el,false),n:1};
  };
  const owner = el => {
    const remembered=window.__infoscreenCardSelector||"";
    if(remembered){try{const x=el.closest(remembered);if(x)return x;}catch{}}
    return el.closest("article,li,[class*='card' i],[class*='tile' i],[class*='event' i],[class*='programme' i],[class*='listing' i],[class*='result' i]");
  };
  const relative = (el,card) => {
    if(!card||!card.contains(el)||card===el)return "";
    const p=[];let cur=el;
    for(let i=0;cur&&cur!==card&&i<8;i++,cur=cur.parentElement)p.unshift(part(cur,false));
    return cur===card?p.join(" > "):"";
  };
  const send = payload => window[args.binding](payload);

  root.querySelectorAll("[data-m]").forEach(b=>b.onclick=()=>setMode(b.dataset.m));
  root.querySelector(".x").onclick=()=>host.remove();
  root.querySelector("[data-a='clear']").onclick=async()=>{ if(confirm("Clear draft?")) status.textContent=(await send({action:"clear_draft"})).message; };
  root.querySelector("[data-a='capture']").onclick=async()=>{ try{status.textContent="Validating listing and detail pages...";status.textContent=(await send({action:"capture_listing"})).message;}catch(e){status.textContent="FAILED: "+e;} };

  document.addEventListener("mousemove",e=>{
    if(mode==="browse"||host.contains(e.target)||!(e.target instanceof Element))return;
    if(hover)hover.style.outline="";hover=e.target;hover.style.outline=`3px solid ${mode==="exclude"?"#ff9a9a":"#8cecff"}`;
  },true);

  document.addEventListener("click",async e=>{
    if(mode==="browse"||host.contains(e.target)||!(e.target instanceof Element))return;
    e.preventDefault();e.stopImmediatePropagation();
    try{
      let el=e.target, selector="", attribute=null, count=1;
      if(mode==="card"||mode==="exclude"){const x=repeated(el);selector=x.s;count=x.n;}
      else if(args.role==="listing"){
        const c=owner(el); if(!c)throw new Error("Select LIST CARD first");
        if(mode==="url"){el=el.closest("a[href]");if(!el)throw new Error("DETAIL LINK must be an anchor");attribute="href";}
        if(mode==="image"){el=el.closest("img");if(!el)throw new Error("IMAGE must be an img");attribute=el.hasAttribute("src")?"src":el.hasAttribute("data-src")?"data-src":"data-lazy-src";}
        selector=relative(el,c); if(!selector)throw new Error("Field must be inside the selected card");
      } else {
        if(mode==="url")throw new Error("DETAIL LINK belongs on the listing");
        if(mode==="image"){el=el.closest("img");if(!el)throw new Error("IMAGE must be an img");attribute=el.hasAttribute("src")?"src":el.hasAttribute("data-src")?"data-src":"data-lazy-src";}
        selector=unique(el);
      }
      const result=await send({action:"select",mode,page_role:args.role,selector,attribute,matched_count:count,page_url:location.href});
      if(mode==="card")window.__infoscreenCardSelector=result.card_selector||selector;
      status.textContent=result.message;setMode("browse");
    }catch(err){status.textContent="FAILED: "+err;}
  },true);
  setMode("browse");
}
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(source_id: str, listing_url: str) -> str:
    return f"{source_id}-{hashlib.sha256(canonical_listing_url(listing_url).encode()).hexdigest()[:12]}"


def _live_dir(root: Path) -> Path:
    path = root / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(root: Path, source_id: str, listing_url: str) -> Path:
    return _live_dir(root) / f"{_key(source_id, listing_url)}.json"


def _read_state(root: Path, source_id: str, listing_url: str) -> dict[str, Any]:
    try:
        value = json.loads(_state_path(root, source_id, listing_url).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(root: Path, source_id: str, listing_url: str, **changes: Any) -> dict[str, Any]:
    path = _state_path(root, source_id, listing_url)
    payload = {
        "source_id": source_id,
        "listing_url": canonical_listing_url(listing_url),
        **_read_state(root, source_id, listing_url),
        **changes,
        "updated_at": _now().isoformat(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return payload


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return pid > 1
    except OSError:
        return False


def start_live_session(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> dict[str, Any]:
    studio_root = Path(root).expanduser().resolve()
    store = LocalEventStudioRuleStore(root=studio_root, source_config_path=source_config_path)
    safe_source, canonical_url = store._binding(source_id, listing_url)
    current = _read_state(studio_root, safe_source, canonical_url)
    if _alive(int(current.get("pid") or 0)):
        return {**current, "ok": True, "already_running": True}

    worker = Path(__file__).resolve().parents[1] / "jobs" / "local_event_studio_live.py"
    log = _live_dir(studio_root) / f"{_key(safe_source, canonical_url)}.log"
    env = os.environ.copy()
    env["INFOSCREEN_ENV_DIR"] = str(studio_root.parent)
    with log.open("ab") as handle:
        proc = subprocess.Popen(
            [sys.executable, str(worker), safe_source, canonical_url],
            cwd=str(worker.parents[1]),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    state = _write_state(
        studio_root, safe_source, canonical_url,
        pid=proc.pid, status="starting", current_url=canonical_url,
        started_at=_now().isoformat(), log_path=str(log),
    )
    return {**state, "ok": True, "already_running": False}


def _source(path: Path, source_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload.get("sources") or []:
        if isinstance(item, dict) and item.get("id") == source_id:
            return dict(item)
    raise ValueError(f"source not found: {source_id}")


def _allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(host and any(
        host == str(d).lower().removeprefix("www.") or host.endswith("." + str(d).lower().removeprefix("www."))
        for d in source.get("allowed_domains") or []
    ))


def _role(url: str, listing_url: str) -> str:
    a, b = urlsplit(url), urlsplit(canonical_listing_url(listing_url))
    return "listing" if (a.netloc.lower(), a.path.rstrip("/")) == (b.netloc.lower(), b.path.rstrip("/")) else "detail"


def _selector(selector: str, attribute: str | None = None, optional: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {"selector": selector, "optional": optional}
    if attribute:
        value["attribute"] = attribute
    return value


def _empty(source_id: str, listing_url: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "source_id": source_id, "listing_url": listing_url,
        "version": 0, "status": "draft", "fields": {},
        "detail_page": {"enabled": False, "fields": {}},
        "validation": {"require_public_detail_url": True, "require_current_or_future_date": True},
    }


def _save_selection(store: LocalEventStudioRuleStore, source_id: str, listing_url: str, data: dict[str, Any]) -> LocalEventStudioRule:
    old = store.load_draft(source_id, listing_url)
    raw = old.model_dump(mode="json", exclude_none=True) if old else _empty(source_id, listing_url)
    mode, role, selector = str(data.get("mode")), str(data.get("page_role")), str(data.get("selector") or "").strip()
    attribute = str(data.get("attribute") or "").strip() or None
    if not selector:
        raise ValueError("empty selector")
    if mode == "card":
        raw["card"] = {"selector": selector, "exclude_selectors": list((raw.get("card") or {}).get("exclude_selectors") or [])}
    elif mode == "exclude":
        card = dict(raw.get("card") or {})
        if not card.get("selector"):
            raise ValueError("select LIST CARD first")
        card["exclude_selectors"] = list(dict.fromkeys([*(card.get("exclude_selectors") or []), selector]))
        raw["card"] = card
    elif mode == "url":
        raw.setdefault("fields", {})["url"] = _selector(selector, "href")
    elif mode in {"title", "when", "where", "summary", "image"}:
        target = raw.setdefault("fields", {})
        if role == "detail":
            detail = raw.setdefault("detail_page", {"enabled": True, "fields": {}})
            detail["enabled"] = True
            target = detail.setdefault("fields", {})
            if mode in {"title", "when", "where"} and mode not in raw["fields"]:
                placeholder = _selector(f"#__infoscreen_detail_only_{mode}", optional=True)
                if mode == "where":
                    placeholder["allow_source_default"] = False
                raw["fields"][mode] = placeholder
        target[mode] = _selector(selector, attribute, optional=mode in {"summary", "image"})
    else:
        raise ValueError(f"unsupported mode: {mode}")
    return store.save_draft(raw)


def _value(locator: Any, attribute: str | None) -> str:
    if locator.count() <= 0:
        return ""
    node = locator.first
    return clean(node.get_attribute(attribute) or "") if attribute else clean(node.inner_text(timeout=3000) or "")


def _validate(page: Any, context: Any, rule: LocalEventStudioRule, source: dict[str, Any]) -> dict[str, Any]:
    fatal, accepted, rejected = [], [], []
    cards = page.locator(rule.card.selector).all() if rule.card else []
    if not cards:
        fatal.append("card_selector_matched_zero_elements")
    if rule.fields.url is None:
        fatal.append("url_selector_missing")
    seen: set[str] = set()
    for index, card in enumerate(cards[:12]):
        if len(accepted) >= 3:
            break
        try:
            if any(card.locator(s).count() > 0 or bool(card.evaluate("(e,s)=>e.matches(s)", s)) for s in (rule.card.exclude_selectors if rule.card else [])):
                continue
            raw_url = _value(card.locator(rule.fields.url.selector), rule.fields.url.attribute)
            public_url, reason = validate_detail_url(raw_url, rule.listing_url, source)
            if reason or public_url in seen:
                raise ValueError(reason or "duplicate_detail_url")
            seen.add(public_url)
            values: dict[str, str] = {"url": public_url}
            for name in ("title","when","where","summary","image"):
                mapping = getattr(rule.fields, name)
                if mapping:
                    values[name] = _value(card.locator(mapping.selector), mapping.attribute)
            if rule.detail_page.enabled:
                detail = context.new_page()
                try:
                    try:
                        detail.goto(public_url, wait_until="networkidle", timeout=20000)
                    except Exception:
                        detail.goto(public_url, wait_until="domcontentloaded", timeout=20000)
                    if not _allowed(str(detail.url), source):
                        raise ValueError("detail_redirected_outside_allowed_domains")
                    for name in ("title","when","where","summary","image"):
                        mapping = getattr(rule.detail_page.fields, name)
                        if mapping:
                            value = _value(detail.locator(mapping.selector), mapping.attribute)
                            if value:
                                values[name] = value
                finally:
                    detail.close()
            reasons = [f"{x}_missing_after_detail" for x in ("title","when","where") if not values.get(x)]
            dates = label_dates(values.get("when",""))
            if not dates:
                reasons.append("when_not_parseable")
            elif rule.validation.require_current_or_future_date and max(dates) < _now().date():
                reasons.append("event_expired")
            if reasons:
                raise ValueError(reasons[0])
            accepted.append({"card_id": f"live-{index}", "event": {
                "title": values["title"], "when": values["when"], "where": values["where"],
                "url": public_url, "summary": values.get("summary",""), "image": values.get("image",""),
                "start_date": min(dates).isoformat(), "source_id": rule.source_id,
                "source_name": source.get("name") or rule.source_id, "listing_url": rule.listing_url,
            }, "detail_page_pending": False})
        except Exception as exc:
            rejected.append({"card_id": f"live-{index}", "reason": str(exc) or type(exc).__name__})
    if len(accepted) < 2:
        fatal.append("live_validation_requires_two_confirmed_detail_pages")
    return {
        "schema_version": 1, "rule_fingerprint": rule_fingerprint(rule),
        "source_id": rule.source_id, "listing_url": rule.listing_url,
        "card_selector": rule.card.selector if rule.card else None,
        "matched_card_count": len(cards), "accepted_count": len(accepted),
        "rejected_count": len(rejected), "publishable": not fatal and len(accepted) >= 2,
        "fatal_errors": fatal, "warnings": [], "accepted": accepted, "rejected": rejected,
        "validation_mode": "operator_live_browser_with_detail_pages",
    }


def run_live_session(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> int:
    studio_root, config_path = Path(root).resolve(), Path(source_config_path).resolve()
    store = LocalEventStudioRuleStore(root=studio_root, source_config_path=config_path)
    safe_source, canonical_url = store._binding(source_id, listing_url)
    source = _source(config_path, safe_source)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _write_state(studio_root, safe_source, canonical_url, status="failed", error=f"missing_playwright:{exc}")
        return 2
    executable = find_browser_executable()
    if not executable:
        _write_state(studio_root, safe_source, canonical_url, status="failed", error="missing_system_chromium")
        return 3

    binding = "__infoscreenStudioBinding"
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(_live_dir(studio_root) / f"{_key(safe_source, canonical_url)}-profile"),
            headless=False, executable_path=executable, viewport=None,
            args=["--no-sandbox","--disable-dev-shm-usage","--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        def capture(current_page: Any) -> dict[str, Any]:
            if _role(str(current_page.url), canonical_url) != "listing":
                raise ValueError("Return to the configured listing first")
            dom, captured = current_page.evaluate(DOM_EVIDENCE_JS, {"maxElements": 6000}), _now()
            snapshot_id = captured.strftime("%Y%m%dT%H%M%S%fZ") + "-" + hashlib.sha256(canonical_url.encode()).hexdigest()[:10]
            metadata = {
                "schema_version": 1, "snapshot_id": snapshot_id, "source_id": safe_source,
                "source_name": source.get("name"), "listing_url": canonical_url,
                "final_url": str(current_page.url), "page_title": current_page.title(),
                "captured_at": captured.isoformat(), "prepare": {"mode":"operator_live_browser"},
                "dom_element_count": int(dom.get("element_count") or 0), "dom_truncated": bool(dom.get("truncated")),
                "assets": {"page.png":"page.png","page.html":"page.html","dom.json":"dom.json","metadata.json":"metadata.json"},
            }
            snapshot = write_snapshot(studio_root, metadata, screenshot=current_page.screenshot(full_page=True, type="png"), html=current_page.content(), dom=dom)
            draft = store.load_draft(safe_source, canonical_url)
            if not draft:
                raise ValueError("Select card, detail link and detail fields first")
            test = _write_test_run(studio_root, _validate(current_page, context, draft, source), snapshot_id)
            return {**snapshot, "test_result": test}

        def callback(source_binding: Any, payload: Any) -> dict[str, Any]:
            data = dict(payload or {})
            current_page = source_binding["page"]
            if data.get("action") == "clear_draft":
                store.delete_draft(safe_source, canonical_url)
                return {"ok": True, "message": "Draft cleared."}
            if data.get("action") == "capture_listing":
                snapshot = capture(current_page)
                test = snapshot["test_result"]
                return {"ok": True, "message": f"Validation {'passed' if test['publishable'] else 'failed'}: {test['accepted_count']} confirmed details."}
            if data.get("action") == "select":
                data["page_role"] = _role(str(current_page.url), canonical_url)
                draft = _save_selection(store, safe_source, canonical_url, data)
                return {"ok": True, "message": f"Saved {data.get('mode')}: {data.get('selector')}", "card_selector": draft.card.selector if draft.card else ""}
            raise ValueError("unsupported action")

        context.expose_binding(binding, callback)

        def install(target: Any) -> None:
            if not _allowed(str(target.url), source):
                return
            target.evaluate(OVERLAY_JS, {"binding":binding,"role":_role(str(target.url),canonical_url)})
            draft = store.load_draft(safe_source, canonical_url)
            if draft and draft.card:
                target.evaluate("s=>window.__infoscreenCardSelector=s", draft.card.selector)

        def configure(target: Any) -> None:
            target.on("domcontentloaded", install)

        for target in context.pages:
            configure(target)
        context.on("page", configure)
        try:
            page.goto(canonical_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(canonical_url, wait_until="commit", timeout=30000)
        page.wait_for_timeout(600)
        install(page)
        _write_state(studio_root, safe_source, canonical_url, pid=os.getpid(), status="running", current_url=canonical_url)
        try:
            while context.pages:
                time.sleep(.5)
        finally:
            _write_state(studio_root, safe_source, canonical_url, status="closed")
            context.close()
    return 0


__all__ = ["run_live_session", "start_live_session"]
