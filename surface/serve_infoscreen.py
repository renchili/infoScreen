#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import json
import mimetypes
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

SURFACE_DIR = Path(__file__).resolve().parent
WEB_DIR = SURFACE_DIR / "web"
ENV_DIR = SURFACE_DIR / ".env"
CONF_DIR = SURFACE_DIR / "conf"

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

LEGACY_LOCAL_EVENT_INLINE_RE = re.compile(
    r"\n?<script\s+id=[\"']local-event-inline-script[\"'][^>]*>[\s\S]*?</script>\s*",
    re.I,
)

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


def runtime_json(name: str):
    default = JSON_DEFAULTS.get(name, {})
    path = runtime_path(name)
    if path.exists():
        return read_json(path, default)
    payload = dict(default) if isinstance(default, dict) else default
    if isinstance(payload, dict):
        payload = {
            **payload,
            "ok": False,
            "error": "missing_runtime_json",
            "expected_path": str(path),
        }
    return payload


def market_config_json():
    path = runtime_path("market_config.json")
    if path.exists():
        return read_json(path, JSON_DEFAULTS["market_config.json"])
    return read_json(CONF_DIR / "market_config.default.json", JSON_DEFAULTS["market_config.json"])


def clean_index_html() -> bytes:
    raw = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    cleaned = LEGACY_LOCAL_EVENT_INLINE_RE.sub("\n", raw)
    cleaned = cleaned.replace('calendar_board.js?v=1781715981', 'calendar_board.js?v=front-clean-1')
    return cleaned.encode("utf-8")


def openapi_payload() -> dict:
    from openapi_spec import build_openapi

    return build_openapi()


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
        data = clean_index_html()
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

        stat = path.stat()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Last-Modified", email.utils.formatdate(stat.st_mtime, usegmt=True))
        self.end_headers()

    def send_env_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Last-Modified", email.utils.formatdate(path.stat().st_mtime, usegmt=True))
        self.end_headers()
        self.wfile.write(data)

    def body_json(self):
        size = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(size).decode("utf-8", "replace") if size else "{}"
        return json.loads(raw or "{}")

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

        if path.startswith("/public_photos/"):
            rel = unquote(path.removeprefix("/public_photos/")).lstrip("/")
            target = ENV_DIR / "public_photos" / rel
            if target.exists() and target.is_file():
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(target.stat().st_size))
                self.send_header("Last-Modified", email.utils.formatdate(target.stat().st_mtime, usegmt=True))
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()
            return

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

        if name in JSON_DEFAULTS:
            return self.send_json(runtime_json(name))

        if path.startswith("/public_photos/"):
            rel = unquote(path.removeprefix("/public_photos/")).lstrip("/")
            return self.send_env_file(ENV_DIR / "public_photos" / rel)

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
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
                proc = subprocess.run([sys.executable, str(SURFACE_DIR / "fetch_live_data.py")], cwd=str(SURFACE_DIR), text=True, capture_output=True, timeout=60)
                return self.send_json({"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:], "market": runtime_json("market.json")}, 200 if proc.returncode == 0 else 500)
            except Exception as exc:
                return self.send_json({"ok": False, "error": str(exc)}, 500)

        if path == "/api/local-events/search":
            try:
                body = self.body_json()
                location = str(body.get("location") or "Punggol Singapore")
                proc = subprocess.run([sys.executable, str(SURFACE_DIR / "search_local_events.py"), location], cwd=str(SURFACE_DIR), text=True, capture_output=True, timeout=130)
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
    print(f"InfoScreen server on 0.0.0.0:8765 from {WEB_DIR}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8765), Handler).serve_forever()


if __name__ == "__main__":
    main()
