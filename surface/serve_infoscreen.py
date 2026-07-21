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
from urllib.parse import unquote, urlparse

try:
    from .local_events_runtime.http1_browser import apply as apply_http1_browser

    apply_http1_browser()

    from .local_events_runtime.event_review import (
        EventReviewStore,
        collect_event_candidates,
        collect_listing_pages,
    )
    from .local_events_runtime.manual_listing import (
        ManualListingRequest,
        add_manual_listing,
    )
except ImportError:
    from local_events_runtime.http1_browser import apply as apply_http1_browser

    apply_http1_browser()

    from local_events_runtime.event_review import (
        EventReviewStore,
        collect_event_candidates,
        collect_listing_pages,
    )
    from local_events_runtime.manual_listing import (
        ManualListingRequest,
        add_manual_listing,
    )

SURFACE_DIR = Path(__file__).resolve().parent
WEB_DIR = SURFACE_DIR / "web"
ENV_DIR = Path(
    os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
).expanduser().resolve()
CONF_DIR = SURFACE_DIR / "conf"
PUBLIC_PHOTO_PREFIX = "/public_photos/"
MAX_JSON_BODY_BYTES = 1_048_576
LOCAL_EVENT_SEARCH_TIMEOUT_SECONDS = int(
    os.environ.get("LOCAL_EVENT_SEARCH_TIMEOUT_SECONDS", "600")
)
REVIEW_MUTATION_LOCK = threading.Lock()

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
    return read_json(
        CONF_DIR / "market_config.default.json",
        JSON_DEFAULTS["market_config.json"],
    )


def index_html() -> bytes:
    return (WEB_DIR / "index.html").read_bytes()


def openapi_payload() -> dict:
    try:
        from .openapi_spec import build_openapi
    except ImportError:
        from openapi_spec import build_openapi
    return build_openapi()


def review_root() -> Path:
    return ENV_DIR / "local_event_review"


def review_store() -> EventReviewStore:
    return EventReviewStore(
        root=review_root(),
        config_path=CONF_DIR / "event_sources.json",
    )


def public_photo_path(request_target: str) -> Path | None:
    """Resolve one public-photo request without permitting traversal or symlinks."""

    request_path = urlparse(request_target).path
    if not request_path.startswith(PUBLIC_PHOTO_PREFIX):
        return None

    encoded_relative = request_path.removeprefix(PUBLIC_PHOTO_PREFIX)
    try:
        decoded_relative = unquote(
            encoded_relative,
            encoding="utf-8",
            errors="strict",
        )
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

    return target if target.is_file() else None


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

    def send_html(
        self,
        html: str,
        status: int = 200,
        head_only: bool = False,
    ) -> None:
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
            return self.send_json(
                {
                    "ok": False,
                    "error": (
                        "openapi_generation_failed: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                },
                500,
            )
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
        self.send_header(
            "Last-Modified",
            email.utils.formatdate(
                (WEB_DIR / "index.html").stat().st_mtime,
                usegmt=True,
            ),
        )
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
        self.send_header(
            "Last-Modified",
            email.utils.formatdate(file_stat.st_mtime, usegmt=True),
        )
        self.end_headers()

    def send_public_photo(self, head_only: bool = False) -> None:
        target = public_photo_path(self.path)
        if target is None:
            self.send_error(404, "not found")
            return

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
            self.send_header(
                "Content-Type",
                mimetypes.guess_type(str(target))[0]
                or "application/octet-stream",
            )
            self.send_header("Content-Length", str(file_stat.st_size))
            self.send_header(
                "Last-Modified",
                email.utils.formatdate(file_stat.st_mtime, usegmt=True),
            )
            self.end_headers()
            if not head_only:
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    shutil.copyfileobj(source, self.wfile)
        finally:
            os.close(descriptor)

    def body_json(self) -> dict:
        size = int(self.headers.get("Content-Length", "0") or "0")
        if size < 0 or size > MAX_JSON_BODY_BYTES:
            raise ValueError("request body exceeds the 1 MiB limit")
        raw = self.rfile.read(size).decode("utf-8", "strict") if size else "{}"
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_HEAD(self):
        path = urlparse(self.path).path
        name = path.lstrip("/")

        if path in {"/", "/index.html"}:
            return self.send_index(head_only=True)
        if path == "/openapi.json":
            return self.send_openapi(head_only=True)
        if path == "/docs":
            return self.send_html(SWAGGER_UI_HTML, head_only=True)
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
            return self.send_json(
                runtime_json("local_event_search_results.json")
            )
        if path == "/api/local-events/review/state":
            try:
                return self.send_json(review_store().state_payload())
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "local_event_review_state_failed",
                        "detail": str(exc),
                    },
                    500,
                )
        if name in JSON_DEFAULTS:
            return self.send_json(runtime_json(name))
        if path.startswith(PUBLIC_PHOTO_PREFIX):
            return self.send_public_photo()
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/local-events/review/discover-listings":
            try:
                with REVIEW_MUTATION_LOCK:
                    state = collect_listing_pages(review_store())
                return self.send_json(
                    {"ok": True, **state.model_dump(mode="json")}
                )
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "listing_page_collection_failed",
                        "detail": str(exc),
                    },
                    500,
                )

        if path == "/api/local-events/review/listing-page":
            try:
                request = ManualListingRequest.model_validate(self.body_json())
                with REVIEW_MUTATION_LOCK:
                    state = add_manual_listing(review_store(), request)
                return self.send_json(
                    {"ok": True, **state.model_dump(mode="json")}
                )
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "manual_listing_page_failed",
                        "detail": str(exc),
                    },
                    400,
                )

        if path == "/api/local-events/review/listing-decision":
            try:
                body = self.body_json()
                candidate_id = str(body.get("candidate_id") or "").strip()
                decision = str(body.get("decision") or "").strip()
                if decision not in {"pending", "confirmed", "rejected"}:
                    raise ValueError("invalid listing decision")
                with REVIEW_MUTATION_LOCK:
                    state = review_store().set_listing_decision(
                        candidate_id,
                        decision,
                    )
                return self.send_json(
                    {"ok": True, **state.model_dump(mode="json")}
                )
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "listing_decision_failed",
                        "detail": str(exc),
                    },
                    400,
                )

        if path == "/api/local-events/review/collect-events":
            try:
                with REVIEW_MUTATION_LOCK:
                    state = collect_event_candidates(review_store())
                return self.send_json(
                    {"ok": True, **state.model_dump(mode="json")}
                )
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "event_candidate_collection_failed",
                        "detail": str(exc),
                    },
                    500,
                )

        if path == "/api/local-events/review/event-decision":
            try:
                body = self.body_json()
                candidate_id = str(body.get("candidate_id") or "").strip()
                decision = str(body.get("decision") or "").strip()
                if decision not in {"pending", "confirmed", "rejected"}:
                    raise ValueError("invalid event decision")
                with REVIEW_MUTATION_LOCK:
                    state = review_store().set_event_decision(
                        candidate_id,
                        decision,
                    )
                return self.send_json(
                    {"ok": True, **state.model_dump(mode="json")}
                )
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "event_decision_failed",
                        "detail": str(exc),
                    },
                    400,
                )

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
                (ENV_DIR / "market_config.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return self.send_json({"ok": True, **payload})
            except Exception as exc:
                return self.send_json(
                    {"ok": False, "error": str(exc)},
                    400,
                )

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
                return self.send_json(
                    {"ok": False, "error": str(exc)},
                    500,
                )

        if path == "/api/local-events/search":
            try:
                body = self.body_json()
                location = (
                    str(body.get("location") or "Punggol Singapore").strip()
                    or "Punggol Singapore"
                )
                environment = os.environ.copy()
                environment["INFOSCREEN_ENV_DIR"] = str(ENV_DIR)
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SURFACE_DIR / "search_local_events.py"),
                        location,
                    ],
                    cwd=str(SURFACE_DIR),
                    text=True,
                    capture_output=True,
                    timeout=LOCAL_EVENT_SEARCH_TIMEOUT_SECONDS,
                    env=environment,
                )
                data = runtime_json("local_event_search_results.json")
                data["ok"] = proc.returncode == 0
                data["returncode"] = proc.returncode
                data["stdout"] = proc.stdout[-1000:]
                data["stderr"] = proc.stderr[-1000:]
                if proc.returncode != 0:
                    data["error"] = "local_event_search_failed"
                return self.send_json(
                    data,
                    200 if proc.returncode == 0 else 500,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = (
                    exc.stdout.decode("utf-8", "replace")
                    if isinstance(exc.stdout, bytes)
                    else str(exc.stdout or "")
                )
                stderr = (
                    exc.stderr.decode("utf-8", "replace")
                    if isinstance(exc.stderr, bytes)
                    else str(exc.stderr or "")
                )
                data = runtime_json("local_event_search_results.json")
                data.update(
                    {
                        "ok": False,
                        "error": "local_event_search_timeout",
                        "detail": (
                            "Local Events exceeded the HTTP limit of "
                            f"{LOCAL_EVENT_SEARCH_TIMEOUT_SECONDS} seconds"
                        ),
                        "stdout": stdout[-1000:],
                        "stderr": stderr[-1000:],
                    }
                )
                return self.send_json(data, 504)
            except Exception as exc:
                return self.send_json(
                    {
                        "ok": False,
                        "error": "local_event_search_request_failed",
                        "detail": str(exc),
                    },
                    500,
                )

        return self.send_json({"ok": False, "error": "not found"}, 404)


def main() -> None:
    ENV_DIR.mkdir(exist_ok=True)
    print(
        f"InfoScreen server on 0.0.0.0:8765 from {WEB_DIR} with env {ENV_DIR}",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", 8765), Handler).serve_forever()


if __name__ == "__main__":
    main()
