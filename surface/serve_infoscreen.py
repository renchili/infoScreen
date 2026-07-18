#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import json
import mimetypes
import os
import shutil
import stat
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

try:
    from .api_models import (
        StudioCaptureRequest,
        StudioRuleBindingRequest,
        StudioRuleImportRequest,
        StudioRuleRollbackRequest,
        StudioTestRequest,
    )
    from .local_events_runtime.studio_capture import list_snapshots, snapshot_asset_path
    from .local_events_runtime.studio_evaluate import (
        StudioEvaluationError,
        latest_test_run,
        require_publishable_test,
        test_draft,
    )
    from .local_events_runtime.studio_rules import (
        LocalEventStudioRuleStore,
        RuleConflictError,
        RuleNotFoundError,
        RuleStorageError,
        UnknownListingError,
        UnknownSourceError,
    )
except ImportError:
    from api_models import (
        StudioCaptureRequest,
        StudioRuleBindingRequest,
        StudioRuleImportRequest,
        StudioRuleRollbackRequest,
        StudioTestRequest,
    )
    from local_events_runtime.studio_capture import list_snapshots, snapshot_asset_path
    from local_events_runtime.studio_evaluate import (
        StudioEvaluationError,
        latest_test_run,
        require_publishable_test,
        test_draft,
    )
    from local_events_runtime.studio_rules import (
        LocalEventStudioRuleStore,
        RuleConflictError,
        RuleNotFoundError,
        RuleStorageError,
        UnknownListingError,
        UnknownSourceError,
    )

SURFACE_DIR = Path(__file__).resolve().parent
WEB_DIR = SURFACE_DIR / "web"
ENV_DIR = Path(os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))).expanduser().resolve()
CONF_DIR = SURFACE_DIR / "conf"
PUBLIC_PHOTO_PREFIX = "/public_photos/"
MAX_JSON_BODY_BYTES = 1_048_576
STUDIO_MUTATION_LOCK = threading.Lock()
STUDIO_CAPTURE_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_EVENT_STUDIO_CAPTURE_TIMEOUT_SECONDS", "180"))

JSON_DEFAULTS = {
    "schedule.json": [],
    "weather.json": {},
    "market.json": {},
    "market_config.json": {"symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]},
    "event_stream.json": {"items": []},
    "local_event_search_results.json": {"results": []},
    "photos.json": {"items": []},
    "sync_status.json": {},
}

SWAGGER_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>InfoScreen API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>body{margin:0;background:#0b0d0e;} .topbar{display:none}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      layout: "BaseLayout"
    });
  </script>
</body>
</html>
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def runtime_path(name: str) -> Path:
    return ENV_DIR / name


def normalize_runtime_payload(name: str, payload):
    if name != "local_event_search_results.json" or not isinstance(payload, dict):
        return payload
    try:
        from .local_events_runtime.output import normalize_payload
    except ImportError:
        from local_events_runtime.output import normalize_payload
    return normalize_payload(payload)


def runtime_json(name: str):
    default = JSON_DEFAULTS.get(name, {})
    path = runtime_path(name)
    if path.exists():
        return normalize_runtime_payload(name, read_json(path, default))
    payload = dict(default) if isinstance(default, dict) else default
    if isinstance(payload, dict):
        payload = {
            **payload,
            "ok": False,
            "error": "missing_runtime_json",
            "expected_path": str(path),
        }
    return normalize_runtime_payload(name, payload)


def market_config_json():
    path = runtime_path("market_config.json")
    if path.exists():
        return read_json(path, JSON_DEFAULTS["market_config.json"])
    return read_json(CONF_DIR / "market_config.default.json", JSON_DEFAULTS["market_config.json"])


def index_html() -> bytes:
    return (WEB_DIR / "index.html").read_bytes()


def openapi_payload() -> dict:
    try:
        from .openapi_spec import build_openapi
    except ImportError:
        from openapi_spec import build_openapi
    return build_openapi()


def studio_root() -> Path:
    return ENV_DIR / "local_event_studio"


def studio_rule_store() -> LocalEventStudioRuleStore:
    """Return a rule store rooted in the active machine-local runtime directory."""

    return LocalEventStudioRuleStore(
        root=studio_root(),
        source_config_path=CONF_DIR / "event_sources.json",
    )


def studio_rule_payload(rule):
    return rule.model_dump(mode="json", exclude_none=True) if rule is not None else None


def studio_sources_payload(store: LocalEventStudioRuleStore | None = None) -> dict:
    """List configured source/listing pairs with only rule-state metadata."""

    active = store or studio_rule_store()
    raw_inventory = read_json(CONF_DIR / "event_sources.json", {"sources": []})
    names = {
        str(item.get("id")): str(item.get("name") or "")
        for item in raw_inventory.get("sources") or []
        if isinstance(item, dict) and item.get("id")
    }
    sources = []
    for source in active.configured_sources():
        listing_states = []
        for listing_url in source.listing_urls:
            draft = active.load_draft(source.id, listing_url)
            published = active.load_published(source.id, listing_url)
            history = active.list_history(source.id, listing_url)
            listing_states.append(
                {
                    "listing_url": listing_url,
                    "has_draft": draft is not None,
                    "published_version": published.version if published else None,
                    "history_versions": [item.version for item in history],
                }
            )
        sources.append(
            {
                "source_id": source.id,
                "name": names.get(source.id) or None,
                "listing_urls": listing_states,
            }
        )
    return {"ok": True, "sources": sources}


def studio_rules_payload(source_id: str, listing_url: str, store: LocalEventStudioRuleStore | None = None) -> dict:
    """Return all persisted rule states for one configured source/listing pair."""

    active = store or studio_rule_store()
    draft = active.load_draft(source_id, listing_url)
    published = active.load_published(source_id, listing_url)
    history = active.list_history(source_id, listing_url)
    canonical_url = active._binding(source_id, listing_url)[1]
    return {
        "ok": True,
        "source_id": source_id,
        "listing_url": canonical_url,
        "draft": studio_rule_payload(draft),
        "published": studio_rule_payload(published),
        "history": [studio_rule_payload(item) for item in history],
    }


def studio_error(exc: Exception) -> tuple[dict, int]:
    if isinstance(exc, UnknownSourceError):
        return {"ok": False, "error": "unknown_source", "detail": str(exc)}, 400
    if isinstance(exc, UnknownListingError):
        return {"ok": False, "error": "unknown_listing", "detail": str(exc)}, 400
    if isinstance(exc, ValidationError):
        return {"ok": False, "error": "invalid_rule", "detail": str(exc)}, 400
    if isinstance(exc, (ValueError, json.JSONDecodeError, UnicodeDecodeError)):
        return {"ok": False, "error": "invalid_request", "detail": str(exc)}, 400
    if isinstance(exc, RuleNotFoundError):
        return {"ok": False, "error": "rule_not_found", "detail": str(exc)}, 404
    if isinstance(exc, StudioEvaluationError):
        return {"ok": False, "error": "studio_test_required", "detail": str(exc)}, 422
    if isinstance(exc, RuleConflictError):
        return {"ok": False, "error": "rule_conflict", "detail": str(exc)}, 409
    if isinstance(exc, RuleStorageError):
        return {"ok": False, "error": "studio_rule_storage_failed"}, 500
    return {"ok": False, "error": "studio_operation_failed"}, 500


def public_photo_path(request_target: str) -> Path | None:
    """Resolve one public-photo request without permitting traversal or symlinks."""
    request_path = urlparse(request_target).path
    if not request_path.startswith(PUBLIC_PHOTO_PREFIX):
        return None

    encoded_relative = request_path.removeprefix(PUBLIC_PHOTO_PREFIX)
    try:
        decoded_relative = unquote(encoded_relative, encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        return None

    if (
        not decoded_relative
        or "\x00" in decoded_relative
        or "\\" in decoded_relative
        or decoded_relative.startswith(("/", "\\"))
    ):
        return None

    raw_parts = decoded_relative.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return None

    relative = PurePosixPath(*raw_parts)
    if relative.is_absolute():
        return None

    public_root = (ENV_DIR / "public_photos").resolve()
    lexical_target = public_root.joinpath(*relative.parts)

    current = public_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None

    try:
        target = lexical_target.resolve(strict=True)
        target.relative_to(public_root)
    except (FileNotFoundError, OSError, ValueError):
        return None

    if not target.is_file():
        return None
    return target


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html: str, status: int = 200, head_only: bool = False) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def send_openapi(self, head_only: bool = False) -> None:
        try:
            payload = openapi_payload()
        except Exception as exc:
            return self.send_json({"ok": False, "error": f"openapi_generation_failed: {type(exc).__name__}: {exc}"}, 500)
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def send_index(self, head_only: bool = False) -> None:
        data = index_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Last-Modified", email.utils.formatdate((WEB_DIR / "index.html").stat().st_mtime, usegmt=True))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def send_json_head(self, name: str) -> None:
        path = runtime_path(name)
        if not path.exists() or not path.is_file():
            self.send_response(404)
            self.end_headers()
            return

        file_stat = path.stat()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(file_stat.st_size))
        self.send_header("Last-Modified", email.utils.formatdate(file_stat.st_mtime, usegmt=True))
        self.end_headers()

    def send_file(self, target: Path, content_type: str, *, head_only: bool = False) -> None:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags)
        except OSError:
            self.send_error(404, "not found")
            return
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                self.send_error(404, "not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_stat.st_size))
            self.send_header("Last-Modified", email.utils.formatdate(file_stat.st_mtime, usegmt=True))
            self.end_headers()
            if not head_only:
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    shutil.copyfileobj(source, self.wfile)
        finally:
            os.close(descriptor)

    def send_public_photo(self, head_only: bool = False) -> None:
        target = public_photo_path(self.path)
        if target is None:
            self.send_error(404, "not found")
            return
        self.send_file(target, mimetypes.guess_type(str(target))[0] or "application/octet-stream", head_only=head_only)

    def send_studio_snapshot_asset(self, head_only: bool = False) -> None:
        try:
            source_id = self.query_value("source_id") or ""
            snapshot_id = self.query_value("snapshot_id") or ""
            asset = self.query_value("asset") or ""
        except Exception as exc:
            return self.send_studio_error(exc)
        target = snapshot_asset_path(source_id, snapshot_id, asset, root=studio_root())
        if target is None:
            return self.send_json({"ok": False, "error": "snapshot_asset_not_found"}, 404)
        content_type = {
            "page.png": "image/png",
            "page.html": "text/html; charset=utf-8",
            "dom.json": "application/json; charset=utf-8",
            "metadata.json": "application/json; charset=utf-8",
        }[asset]
        return self.send_file(target, content_type, head_only=head_only)

    def body_json(self):
        size = int(self.headers.get("Content-Length", "0") or "0")
        if size < 0 or size > MAX_JSON_BODY_BYTES:
            raise ValueError("request body exceeds the 1 MiB limit")
        raw = self.rfile.read(size).decode("utf-8", "strict") if size else "{}"
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def query_value(self, name: str, *, required: bool = True) -> str | None:
        values = parse_qs(urlparse(self.path).query, keep_blank_values=True).get(name, [])
        value = values[0].strip() if values else ""
        if required and not value:
            raise ValueError(f"missing query parameter: {name}")
        return value or None

    def send_studio_error(self, exc: Exception) -> None:
        payload, status = studio_error(exc)
        self.send_json(payload, status)

    def do_HEAD(self):
        path = urlparse(self.path).path
        name = path.lstrip("/")

        if path in {"/", "/index.html"}:
            return self.send_index(head_only=True)
        if path == "/openapi.json":
            return self.send_openapi(head_only=True)
        if path == "/docs":
            return self.send_html(SWAGGER_UI_HTML, head_only=True)
        if path == "/api/local-events/studio/snapshot-asset":
            return self.send_studio_snapshot_asset(head_only=True)

        if name in JSON_DEFAULTS:
            return self.send_json_head(name)
        if path.startswith(PUBLIC_PHOTO_PREFIX):
            return self.send_public_photo(head_only=True)
        return super().do_HEAD()

    def do_GET(self):
        path = urlparse(self.path).path
        name = path.lstrip("/")

        if path in {"/", "/index.html"}:
            return self.send_index()
        if path == "/openapi.json":
            return self.send_openapi()
        if path == "/docs":
            return self.send_html(SWAGGER_UI_HTML)
        if path == "/api/market-config":
            return self.send_json(market_config_json())
        if path == "/api/local-events/search":
            return self.send_json(runtime_json("local_event_search_results.json"))
        if path == "/api/local-events/studio/sources":
            try:
                return self.send_json(studio_sources_payload())
            except Exception as exc:
                return self.send_studio_error(exc)
        if path == "/api/local-events/studio/rules":
            try:
                return self.send_json(
                    studio_rules_payload(
                        self.query_value("source_id") or "",
                        self.query_value("listing_url") or "",
                    )
                )
            except Exception as exc:
                return self.send_studio_error(exc)
        if path == "/api/local-events/studio/export":
            try:
                source_id = self.query_value("source_id") or ""
                listing_url = self.query_value("listing_url") or ""
                status_value = self.query_value("status", required=False) or "published"
                if status_value not in {"draft", "published"}:
                    raise ValueError("status must be draft or published")
                version_text = self.query_value("version", required=False)
                version = int(version_text) if version_text else None
                exported = studio_rule_store().export_rule(
                    source_id,
                    listing_url,
                    status=status_value,
                    version=version,
                )
                return self.send_json({"ok": True, "rule": json.loads(exported)})
            except Exception as exc:
                return self.send_studio_error(exc)
        if path == "/api/local-events/studio/snapshots":
            try:
                snapshots = list_snapshots(
                    root=studio_root(),
                    source_id=self.query_value("source_id", required=False),
                    listing_url=self.query_value("listing_url", required=False),
                )
                return self.send_json({"ok": True, "snapshots": snapshots})
            except Exception as exc:
                return self.send_studio_error(exc)
        if path == "/api/local-events/studio/snapshot-asset":
            return self.send_studio_snapshot_asset()
        if path == "/api/local-events/studio/test-latest":
            try:
                source_id = self.query_value("source_id") or ""
                listing_url = self.query_value("listing_url") or ""
                _, canonical_url = studio_rule_store()._binding(source_id, listing_url)
                result = latest_test_run(source_id, root=studio_root())
                if result is not None and result.get("listing_url") != canonical_url:
                    result = None
                return self.send_json({"ok": True, "result": result})
            except Exception as exc:
                return self.send_studio_error(exc)

        if name in JSON_DEFAULTS:
            return self.send_json(runtime_json(name))
        if path.startswith(PUBLIC_PHOTO_PREFIX):
            return self.send_public_photo()
        return super().do_GET()

    def do_PUT(self):
        path = urlparse(self.path).path
        if path != "/api/local-events/studio/draft":
            return self.send_json({"ok": False, "error": "not found"}, 404)
        try:
            body = self.body_json()
            with STUDIO_MUTATION_LOCK:
                rule = studio_rule_store().save_draft(body)
            return self.send_json({"ok": True, "rule": studio_rule_payload(rule)})
        except Exception as exc:
            return self.send_studio_error(exc)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path != "/api/local-events/studio/draft":
            return self.send_json({"ok": False, "error": "not found"}, 404)
        try:
            request = StudioRuleBindingRequest.model_validate(self.body_json())
            with STUDIO_MUTATION_LOCK:
                deleted = studio_rule_store().delete_draft(request.source_id, request.listing_url)
            return self.send_json({"ok": True, "deleted": deleted})
        except Exception as exc:
            return self.send_studio_error(exc)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/local-events/studio/test":
            try:
                request = StudioTestRequest.model_validate(self.body_json())
                with STUDIO_MUTATION_LOCK:
                    result = test_draft(
                        request.source_id,
                        request.listing_url,
                        request.snapshot_id,
                        root=studio_root(),
                        source_config_path=CONF_DIR / "event_sources.json",
                    )
                return self.send_json({"ok": True, "result": result})
            except Exception as exc:
                return self.send_studio_error(exc)

        if path == "/api/local-events/studio/publish":
            try:
                request = StudioRuleBindingRequest.model_validate(self.body_json())
                with STUDIO_MUTATION_LOCK:
                    store = studio_rule_store()
                    draft = store.load_draft(request.source_id, request.listing_url)
                    if draft is None:
                        raise RuleNotFoundError("draft not found")
                    require_publishable_test(draft, root=studio_root())
                    rule = store.publish(request.source_id, request.listing_url)
                return self.send_json({"ok": True, "rule": studio_rule_payload(rule)})
            except Exception as exc:
                return self.send_studio_error(exc)

        if path == "/api/local-events/studio/rollback":
            try:
                request = StudioRuleRollbackRequest.model_validate(self.body_json())
                with STUDIO_MUTATION_LOCK:
                    rule = studio_rule_store().rollback(request.source_id, request.listing_url, request.version)
                return self.send_json({"ok": True, "rule": studio_rule_payload(rule)})
            except Exception as exc:
                return self.send_studio_error(exc)

        if path == "/api/local-events/studio/import":
            try:
                request = StudioRuleImportRequest.model_validate(self.body_json())
                with STUDIO_MUTATION_LOCK:
                    rule = studio_rule_store().import_draft(request.rule)
                return self.send_json({"ok": True, "rule": studio_rule_payload(rule)})
            except Exception as exc:
                return self.send_studio_error(exc)

        if path == "/api/local-events/studio/capture":
            try:
                request = StudioCaptureRequest.model_validate(self.body_json())
                environment = os.environ.copy()
                environment["INFOSCREEN_ENV_DIR"] = str(ENV_DIR)
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SURFACE_DIR / "jobs" / "local_event_studio_capture.py"),
                        request.source_id,
                        request.listing_url,
                    ],
                    cwd=str(SURFACE_DIR),
                    text=True,
                    capture_output=True,
                    timeout=STUDIO_CAPTURE_TIMEOUT_SECONDS,
                    env=environment,
                )
                if proc.returncode != 0:
                    return self.send_json(
                        {
                            "ok": False,
                            "error": "studio_capture_failed",
                            "detail": proc.stderr[-2000:] or proc.stdout[-2000:],
                        },
                        500,
                    )
                lines = [line for line in proc.stdout.splitlines() if line.strip()]
                if not lines:
                    raise ValueError("capture job returned no JSON result")
                payload = json.loads(lines[-1])
                if payload.get("ok") is not True or not isinstance(payload.get("snapshot"), dict):
                    raise ValueError("capture job returned an invalid result")
                return self.send_json(payload)
            except Exception as exc:
                return self.send_studio_error(exc)

        if path == "/api/market-config":
            try:
                ENV_DIR.mkdir(exist_ok=True)
                body = self.body_json()
                raw = body.get("symbols", [])
                if not isinstance(raw, list):
                    raise ValueError("symbols must be list")
                symbols = []
                for value in raw:
                    symbol = str(value).strip().upper()
                    if symbol and symbol not in symbols:
                        symbols.append(symbol)
                symbols = symbols[:12]
                if not symbols:
                    raise ValueError("empty symbols")
                payload = {"symbols": symbols, "updated_at": now()}
                (ENV_DIR / "market_config.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                return self.send_json({"ok": True, **payload})
            except Exception as exc:
                return self.send_json({"ok": False, "error": str(exc)}, 400)

        if path == "/api/market-refresh":
            try:
                proc = subprocess.run(
                    [sys.executable, str(SURFACE_DIR / "fetch_live_data.py")],
                    cwd=str(SURFACE_DIR),
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                return self.send_json(
                    {
                        "ok": proc.returncode == 0,
                        "returncode": proc.returncode,
                        "stdout": proc.stdout[-2000:],
                        "stderr": proc.stderr[-2000:],
                        "market": runtime_json("market.json"),
                        "weather": runtime_json("weather.json"),
                    },
                    200 if proc.returncode == 0 else 500,
                )
            except Exception as exc:
                return self.send_json({"ok": False, "error": str(exc)}, 500)

        if path == "/api/local-events/search":
            try:
                body = self.body_json()
                location = str(body.get("location") or "Punggol Singapore")
                proc = subprocess.run(
                    [sys.executable, str(SURFACE_DIR / "search_local_events.py"), location],
                    cwd=str(SURFACE_DIR),
                    text=True,
                    capture_output=True,
                    timeout=330,
                )
                data = runtime_json("local_event_search_results.json")
                data["ok"] = proc.returncode == 0
                data["stdout"] = proc.stdout[-1000:]
                data["stderr"] = proc.stderr[-1000:]
                return self.send_json(data, 200 if proc.returncode == 0 else 500)
            except Exception as exc:
                return self.send_json({"ok": False, "error": str(exc)}, 500)

        return self.send_json({"ok": False, "error": "not found"}, 404)


def main() -> None:
    ENV_DIR.mkdir(exist_ok=True)
    print(f"InfoScreen server on 0.0.0.0:8765 from {WEB_DIR} with env {ENV_DIR}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8765), Handler).serve_forever()


if __name__ == "__main__":
    main()
