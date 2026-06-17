import urllib.parse
#!/usr/bin/env python3
import json
import re
import sys
import subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
MARKET_CONFIG = BASE / "market_config.json"


def normalize_symbols(data):
    if isinstance(data, dict):
        raw = data.get("symbols", [])
    elif isinstance(data, list):
        raw = data
    else:
        raw = []

    clean = []
    for item in raw:
        for part in re.split(r"[\s,，;；]+", str(item).strip()):
            symbol = part.upper().strip()
            if not symbol:
                continue
            if not re.match(r"^[A-Z0-9.^=_-]{1,18}$", symbol):
                continue
            if symbol not in clean:
                clean.append(symbol)

    return clean[:20] or ["AAPL", "NVDA", "TSLA", "SPY", "QQQ"]


def read_market_config():
    if not MARKET_CONFIG.exists():
        return normalize_symbols([])

    try:
        return normalize_symbols(json.loads(MARKET_CONFIG.read_text()))
    except Exception:
        return normalize_symbols([])


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = urlparse(path).path
        return str(BASE / path.lstrip("/"))

    def write_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body or "{}")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/market-config":
            self.write_json({"symbols": read_market_config()})
            return

        return super().do_GET()

    def do_POST(self):

        req_path = urllib.parse.urlparse(self.path).path

        if req_path == "/api/local-events/search":
            cache_path = BASE / "local_event_search_results.json"

            def send_json_obj(obj, status=200):
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
                try:
                    payload = json.loads(raw_body or "{}")
                except Exception:
                    payload = {}

                force = bool(payload.get("force"))

                # 前端默认直接读缓存，不能每次打开页面都实时搜 DDG
                if cache_path.exists() and not force:
                    try:
                        cached = json.loads(cache_path.read_text())
                        cached["from_cache"] = True
                        send_json_obj(cached)
                        return
                    except Exception:
                        pass

                try:
                    proc = subprocess.run(
                        [sys.executable, str(BASE / "search_local_events.py")],
                        input=json.dumps(payload, ensure_ascii=False),
                        text=True,
                        cwd=str(BASE),
                        timeout=25,
                        capture_output=True,
                        check=False,
                    )

                    if proc.stdout.strip():
                        try:
                            out = json.loads(proc.stdout)
                            out["from_cache"] = False
                            send_json_obj(out)
                            return
                        except Exception:
                            pass

                    # 脚本失败也回缓存
                    if cache_path.exists():
                        cached = json.loads(cache_path.read_text())
                        cached["from_cache"] = True
                        cached["search_error"] = proc.stderr.strip() or f"search exited {proc.returncode}"
                        send_json_obj(cached)
                        return

                    send_json_obj({
                        "results": [],
                        "error": proc.stderr.strip() or f"search exited {proc.returncode}",
                    })
                    return

                except subprocess.TimeoutExpired:
                    if cache_path.exists():
                        cached = json.loads(cache_path.read_text())
                        cached["from_cache"] = True
                        cached["search_error"] = "search timed out; returned cache"
                        send_json_obj(cached)
                        return

                    send_json_obj({
                        "results": [],
                        "error": "search timed out and no cache exists",
                    })
                    return

            except Exception as exc:
                send_json_obj({
                    "results": [],
                    "error": str(exc),
                }, status=500)
                return


        if req_path == "/api/local-events/search":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"

                try:
                    payload = json.loads(raw_body or "{}")
                except Exception:
                    payload = {}

                proc = subprocess.run(
                    [sys.executable, str(BASE / "search_local_events.py")],
                    input=json.dumps(payload, ensure_ascii=False),
                    text=True,
                    cwd=str(BASE),
                    timeout=150,
                    capture_output=True,
                    check=False,
                )

                if proc.stdout.strip():
                    try:
                        out = json.loads(proc.stdout)
                    except Exception:
                        out = {
                            "results": [],
                            "error": "search script returned invalid JSON",
                            "stdout": proc.stdout[-1000:],
                            "stderr": proc.stderr[-1000:],
                        }
                else:
                    out = {
                        "results": [],
                        "error": proc.stderr.strip() or f"search script exited {proc.returncode}",
                    }

                data = json.dumps(out, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            except Exception as exc:
                data = json.dumps({
                    "results": [],
                    "error": str(exc),
                }, ensure_ascii=False).encode("utf-8")

                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        path = urlparse(self.path).path

        if path == "/api/market-config":
            try:
                symbols = normalize_symbols(self.read_json_body())
            except Exception as exc:
                self.write_json({"error": str(exc)}, status=400)
                return

            MARKET_CONFIG.write_text(json.dumps({"symbols": symbols}, ensure_ascii=False, indent=2))

            fetcher = BASE / "fetch_live_data.py"
            if fetcher.exists():
                subprocess.run(
                    [sys.executable, str(fetcher)],
                    cwd=str(BASE),
                    timeout=30,
                    check=False,
                )

            self.write_json({"symbols": symbols})
            return

        self.write_json({"error": "not found", "path": path}, status=404)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 8765), Handler)
    print("InfoScreen HTTP/API server listening on http://0.0.0.0:8765", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
