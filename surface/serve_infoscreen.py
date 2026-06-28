#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
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


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def send_json(self, obj, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_env_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body_json(self):
        size = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(size).decode("utf-8", "replace") if size else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        path = urlparse(self.path).path
        name = path.lstrip("/")

        if path == "/api/market-config":
            return self.send_json(
                read_json(ENV_DIR / "market_config.json", read_json(CONF_DIR / "market_config.default.json", JSON_DEFAULTS["market_config.json"]))
            )
        if path == "/api/local-events/search":
            return self.send_json(read_json(ENV_DIR / "local_event_search_results.json", JSON_DEFAULTS["local_event_search_results.json"]))

        if name in JSON_DEFAULTS:
            return self.send_json(read_json(ENV_DIR / name, JSON_DEFAULTS[name]))

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
                return self.send_json({"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:], "market": read_json(ENV_DIR / "market.json", {})}, 200 if proc.returncode == 0 else 500)
            except Exception as exc:
                return self.send_json({"ok": False, "error": str(exc)}, 500)

        if path == "/api/local-events/search":
            try:
                body = self.body_json()
                location = str(body.get("location") or "Punggol Singapore")
                proc = subprocess.run([sys.executable, str(SURFACE_DIR / "search_local_events.py"), location], cwd=str(SURFACE_DIR), text=True, capture_output=True, timeout=90)
                data = read_json(ENV_DIR / "local_event_search_results.json", {"results": []})
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
