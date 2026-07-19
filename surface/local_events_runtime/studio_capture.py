from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .browser import DOM_TIMEOUT_MS, NAV_TIMEOUT_MS, PREPARE_PAGE_JS, launch_chromium
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRuleStore,
    RuleConflictError,
    RuleStorageError,
    canonical_listing_url,
)

MAX_DOM_ELEMENTS = int(os.environ.get("LOCAL_EVENT_STUDIO_MAX_DOM_ELEMENTS", "6000"))
LOAD_MORE_ROUNDS = int(os.environ.get("LOCAL_EVENT_STUDIO_LOAD_MORE_ROUNDS", "12"))
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SNAPSHOT_ID_RE = re.compile(r"^\d{8}T\d{12}Z-[a-f0-9]{10}$")
SNAPSHOT_ASSETS = {"page.png", "page.html", "dom.json", "metadata.json"}

DOM_EVIDENCE_JS = r"""
(args) => {
  const maxElements = Number(args.maxElements || 6000);
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, (ch) => "\\" + ch);
  };
  const stableName = (value) => /^[a-zA-Z_][a-zA-Z0-9_-]{0,120}$/.test(String(value || ""));
  const stableAttributeValue = (value) => /^[a-zA-Z0-9_.:-]{1,160}$/.test(String(value || ""));

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width >= 2 && rect.height >= 2 && rect.bottom >= 0 && rect.right >= 0;
  }

  function elementSelector(el) {
    if (stableName(el.id)) return "#" + cssEscape(el.id);
    for (const attr of ["data-testid", "data-test", "data-component", "data-module"]) {
      const value = el.getAttribute(attr);
      if (value && stableAttributeValue(value)) {
        return `${el.tagName.toLowerCase()}[${attr}="${value}"]`;
      }
    }

    const parts = [];
    let current = el;
    for (let depth = 0; current && current !== document.body && depth < 6; depth += 1) {
      let part = current.tagName.toLowerCase();
      const classes = Array.from(current.classList || [])
        .filter(stableName)
        .filter((name) => !/^(active|selected|open|hover|focus|loaded|visible|hidden)$/i.test(name))
        .slice(0, 2);
      if (classes.length) part += "." + classes.map(cssEscape).join(".");
      const siblings = current.parentElement
        ? Array.from(current.parentElement.children).filter((item) => item.tagName === current.tagName)
        : [];
      if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      parts.unshift(part);
      const candidate = parts.join(" > ");
      try {
        if (document.querySelectorAll(candidate).length === 1) return candidate;
      } catch (error) {}
      current = current.parentElement;
    }
    return parts.join(" > ");
  }

  const all = Array.from(document.querySelectorAll("body *"));
  const candidates = all.filter((el) => {
    if (!visible(el)) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width * rect.height < 16) return false;
    const tag = el.tagName.toLowerCase();
    const text = clean(el.innerText || el.textContent || "");
    return Boolean(
      text ||
      el.hasAttribute("href") ||
      el.hasAttribute("src") ||
      el.hasAttribute("data-src") ||
      el.hasAttribute("data-lazy-src") ||
      ["main", "article", "section", "li", "a", "button", "h1", "h2", "h3", "h4", "time", "img"].includes(tag)
    );
  });

  const selected = candidates.slice(0, maxElements);
  selected.forEach((el, index) => {
    el.setAttribute("data-infoscreen-studio-id", `e${String(index + 1).padStart(5, "0")}`);
  });

  const elements = selected.map((el) => {
    const rect = el.getBoundingClientRect();
    const parent = el.parentElement && el.parentElement.closest("[data-infoscreen-studio-id]");
    const attributes = {};
    for (const name of [
      "id", "class", "role", "aria-label", "title", "href", "src", "datetime",
      "data-testid", "data-test", "data-component", "data-module", "data-src", "data-lazy-src"
    ]) {
      const value = el.getAttribute(name);
      if (value) attributes[name] = clean(value).slice(0, 500);
    }
    let href = "";
    if (el.hasAttribute("href")) {
      try { href = new URL(el.getAttribute("href"), document.location.href).href; } catch (error) {}
    }
    let src = "";
    if (el.hasAttribute("src")) {
      try { src = new URL(el.getAttribute("src"), document.location.href).href; } catch (error) {}
    }
    return {
      id: el.getAttribute("data-infoscreen-studio-id"),
      parent_id: parent ? parent.getAttribute("data-infoscreen-studio-id") : null,
      tag: el.tagName.toLowerCase(),
      selector: elementSelector(el),
      text: clean(el.innerText || el.textContent || "").slice(0, 800),
      href,
      src,
      attributes,
      rect: {
        x: Math.round((rect.left + window.scrollX) * 100) / 100,
        y: Math.round((rect.top + window.scrollY) * 100) / 100,
        width: Math.round(rect.width * 100) / 100,
        height: Math.round(rect.height * 100) / 100
      }
    };
  });

  const documentElement = document.documentElement;
  const body = document.body;
  return {
    schema_version: 1,
    page: {
      title: document.title || "",
      url: document.location.href,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      document_width: Math.max(documentElement.scrollWidth, body ? body.scrollWidth : 0),
      document_height: Math.max(documentElement.scrollHeight, body ? body.scrollHeight : 0)
    },
    candidate_count: candidates.length,
    element_count: elements.length,
    truncated: candidates.length > elements.length,
    elements
  };
}
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _source_record(source_config_path: Path, source_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(source_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleStorageError(f"invalid source configuration: {exc}") from exc
    for source in payload.get("sources") or []:
        if isinstance(source, dict) and source.get("id") == source_id:
            return dict(source)
    raise RuleStorageError(f"configured source record missing: {source_id}")


def _host_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in allowed_domains
        )
    )


def make_snapshot_id(source_id: str, listing_url: str, captured_at: datetime) -> str:
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("source_id is not safe for snapshot storage")
    instant = captured_at.astimezone(timezone.utc)
    timestamp = instant.strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(canonical_listing_url(listing_url).encode("utf-8")).hexdigest()[:10]
    return f"{timestamp}-{digest}"


def capture_browser_page(source: dict[str, Any], listing_url: str) -> dict[str, Any]:
    """Render one configured listing and return screenshot, HTML, and DOM evidence."""

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on deployment image
        raise RuntimeError("missing_playwright_python_package") from exc

    allowed_domains = [str(item) for item in source.get("allowed_domains") or []]
    load_more_rounds = int(source.get("load_more_rounds", LOAD_MORE_ROUNDS))

    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            try:
                page.goto(listing_url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            except Exception:
                page.goto(listing_url, wait_until="domcontentloaded", timeout=DOM_TIMEOUT_MS)
            page.wait_for_timeout(700)
            prepare = page.evaluate(PREPARE_PAGE_JS, {"maxRounds": load_more_rounds})
            final_url = str(page.url)
            if not _host_allowed(final_url, allowed_domains):
                raise RuntimeError("listing_redirected_outside_allowed_domains")
            dom = page.evaluate(DOM_EVIDENCE_JS, {"maxElements": MAX_DOM_ELEMENTS})
            html = page.content()
            screenshot = page.screenshot(full_page=True, type="png")
            return {
                "final_url": final_url,
                "page_title": str(page.title() or ""),
                "prepare": prepare,
                "dom": dom,
                "html": html,
                "screenshot": screenshot,
            }
        finally:
            browser.close()


def _write_file(path: Path, content: bytes | str) -> None:
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs = {} if isinstance(content, bytes) else {"encoding": "utf-8"}
    with path.open(mode, **kwargs) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_file(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _snapshot_parent(root: Path, source_id: str) -> Path:
    snapshots_root = root.expanduser().resolve() / "snapshots"
    if snapshots_root.is_symlink():
        raise RuleStorageError("snapshot root must not be a symlink")
    snapshots_root.mkdir(parents=True, exist_ok=True)
    parent = snapshots_root / source_id
    if parent.is_symlink():
        raise RuleStorageError("snapshot source directory must not be a symlink")
    parent.mkdir(parents=True, exist_ok=True)
    try:
        parent.resolve().relative_to(snapshots_root.resolve())
    except ValueError as exc:
        raise RuleStorageError("snapshot source directory escapes the Studio root") from exc
    return parent


def write_snapshot(
    root: Path,
    metadata: dict[str, Any],
    *,
    screenshot: bytes,
    html: str,
    dom: dict[str, Any],
) -> dict[str, Any]:
    source_id = str(metadata.get("source_id") or "")
    snapshot_id = str(metadata.get("snapshot_id") or "")
    if not SOURCE_ID_RE.fullmatch(source_id) or not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise RuleStorageError("unsafe snapshot identity")
    if not screenshot.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuleStorageError("snapshot screenshot is not PNG data")
    if not html.strip() or not isinstance(dom, dict):
        raise RuleStorageError("snapshot HTML and DOM evidence are required")

    parent = _snapshot_parent(root, source_id)
    target = parent / snapshot_id
    if target.is_symlink():
        raise RuleStorageError("snapshot target must not be a symlink")
    if target.exists():
        raise RuleConflictError(f"snapshot already exists: {snapshot_id}")
    temporary = parent / f".{snapshot_id}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir(mode=0o700)
    try:
        _write_file(temporary / "page.png", screenshot)
        _write_file(temporary / "page.html", html)
        _write_json(temporary / "dom.json", dom)
        _write_json(temporary / "metadata.json", metadata)
        _fsync_directory(temporary)
        os.replace(temporary, target)
        _fsync_directory(parent)
    finally:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink(missing_ok=True)
            temporary.rmdir()
    return dict(metadata)


def capture_snapshot(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
    capture_page: Callable[[dict[str, Any], str], dict[str, Any]] = capture_browser_page,
    now_fn: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Validate, capture, and atomically persist one official listing snapshot."""

    studio_root = Path(root).expanduser().resolve()
    config_path = Path(source_config_path).expanduser().resolve()
    store = LocalEventStudioRuleStore(root=studio_root, source_config_path=config_path)
    safe_source, canonical_url = store._binding(source_id, listing_url)
    source = _source_record(config_path, safe_source)
    result = capture_page(source, canonical_url)
    captured_at = now_fn().astimezone(timezone.utc)
    snapshot_id = make_snapshot_id(safe_source, canonical_url, captured_at)

    screenshot = result.get("screenshot")
    html = result.get("html")
    dom = result.get("dom")
    if not isinstance(screenshot, bytes) or not isinstance(html, str) or not isinstance(dom, dict):
        raise RuleStorageError("capture result is missing screenshot, HTML, or DOM evidence")

    metadata = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "source_id": safe_source,
        "source_name": source.get("name"),
        "listing_url": canonical_url,
        "final_url": str(result.get("final_url") or canonical_url),
        "page_title": str(result.get("page_title") or ""),
        "captured_at": captured_at.isoformat(),
        "prepare": result.get("prepare") or {},
        "dom_element_count": int(dom.get("element_count") or 0),
        "dom_truncated": bool(dom.get("truncated")),
        "assets": {
            "screenshot": "page.png",
            "html": "page.html",
            "dom": "dom.json",
        },
    }
    return write_snapshot(
        studio_root,
        metadata,
        screenshot=screenshot,
        html=html,
        dom=dom,
    )


def list_snapshots(
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_id: str | None = None,
    listing_url: str | None = None,
) -> list[dict[str, Any]]:
    studio_root = Path(root).expanduser().resolve()
    if source_id is not None and not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("invalid source_id")
    wanted_listing = canonical_listing_url(listing_url) if listing_url else None
    snapshots_root = studio_root / "snapshots"
    if snapshots_root.is_symlink():
        raise RuleStorageError("snapshot root must not be a symlink")
    candidates = [snapshots_root / source_id] if source_id else list(snapshots_root.glob("*"))
    output: list[dict[str, Any]] = []
    for source_dir in candidates:
        if source_dir.is_symlink() or not source_dir.is_dir() or not SOURCE_ID_RE.fullmatch(source_dir.name):
            continue
        for metadata_path in source_dir.glob("*/metadata.json"):
            if (
                metadata_path.is_symlink()
                or metadata_path.parent.is_symlink()
                or not SNAPSHOT_ID_RE.fullmatch(metadata_path.parent.name)
            ):
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata_listing = canonical_listing_url(metadata.get("listing_url"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if metadata.get("source_id") != source_dir.name:
                continue
            if metadata.get("snapshot_id") != metadata_path.parent.name:
                continue
            if wanted_listing and metadata_listing != wanted_listing:
                continue
            output.append(metadata)
    output.sort(key=lambda item: str(item.get("captured_at") or ""), reverse=True)
    return output


def snapshot_asset_path(
    source_id: str,
    snapshot_id: str,
    asset: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
) -> Path | None:
    if not SOURCE_ID_RE.fullmatch(source_id) or not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        return None
    if asset not in SNAPSHOT_ASSETS:
        return None
    studio_root = Path(root).expanduser().resolve()
    snapshots_root = (studio_root / "snapshots").resolve()
    target = snapshots_root / source_id / snapshot_id / asset
    current = snapshots_root
    for part in (source_id, snapshot_id, asset):
        current = current / part
        if current.is_symlink():
            return None
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(snapshots_root)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


__all__ = [
    "DOM_EVIDENCE_JS",
    "MAX_DOM_ELEMENTS",
    "SNAPSHOT_ASSETS",
    "capture_browser_page",
    "capture_snapshot",
    "list_snapshots",
    "make_snapshot_id",
    "snapshot_asset_path",
    "write_snapshot",
]
