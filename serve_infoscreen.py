#!/usr/bin/env python3
import json
import subprocess
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent

def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body_json(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/market-config":
            data = read_json(BASE / "market_config.json", {"symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]})
            return self.send_json(data)

        if path == "/api/local-events/search":
            cache = BASE / "local_event_search_results.json"
            return self.send_json(read_json(cache, {"results": []}))

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/market-config":
            try:
                body = self.read_body_json()
                symbols = body.get("symbols", [])
                if not isinstance(symbols, list):
                    raise ValueError("symbols must be list")

                clean = []
                for s in symbols:
                    s = str(s).strip().upper()
                    if s and s not in clean:
                        clean.append(s)

                clean = clean[:12]
                if not clean:
                    raise ValueError("empty symbols")

                payload = {
                    "symbols": clean,
                    "updated_at": time_now(),
                }
                (BASE / "market_config.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
                return self.send_json({"ok": True, **payload})
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 400)

        if path == "/api/market-refresh":
            try:
                p = subprocess.run(
                    [sys.executable, str(BASE / "fetch_live_data.py")],
                    cwd=str(BASE),
                    text=True,
                    capture_output=True,
                    timeout=40,
                )
                return self.send_json({
                    "ok": p.returncode == 0,
                    "returncode": p.returncode,
                    "stdout": p.stdout[-2000:],
                    "stderr": p.stderr[-2000:],
                }, 200 if p.returncode == 0 else 500)
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 500)

        if path == "/api/local-events/search":
            try:
                body = self.read_body_json()
                location = str(body.get("location") or "Punggol Singapore")
                p = subprocess.run(
                    [sys.executable, str(BASE / "search_local_events.py"), location],
                    cwd=str(BASE),
                    text=True,
                    capture_output=True,
                    timeout=80,
                )
                data = read_json(BASE / "local_event_search_results.json", {"results": []})
                data["ok"] = p.returncode == 0
                data["stdout"] = p.stdout[-1000:]
                data["stderr"] = p.stderr[-1000:]
                return self.send_json(data, 200 if p.returncode == 0 else 500)
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 500)

        return self.send_json({"ok": False, "error": "not found"}, 404)

def time_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def main():
    host = "0.0.0.0"
    port = 8765
    print(f"InfoScreen serving http://{host}:{port}/ from {BASE}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__":
    main()
