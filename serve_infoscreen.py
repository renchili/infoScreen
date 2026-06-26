#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
PLACEHOLDER_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
LOCAL_EVENT_TEXT_FIELDS = {
    "title",
    "poster_title",
    "what",
    "what_text",
    "name",
    "event",
    "summary",
    "poster_summary",
    "why",
    "why_text",
    "description",
    "desc",
    "when",
    "when_text",
    "date",
    "date_text",
    "time",
    "time_text",
    "venue",
    "where",
    "where_text",
    "location",
    "address",
    "source",
    "source_name",
    "who",
    "who_text",
    "organizer",
    "host",
    "how",
    "how_text",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    text = str(value or "")
    text = PLACEHOLDER_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def sanitize_value(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return sanitize_dict(value)
    return value


def sanitize_dict(obj):
    out = {}
    for key, value in obj.items():
        if key in LOCAL_EVENT_TEXT_FIELDS:
            out[key] = clean_text(value)
        else:
            out[key] = sanitize_value(value)
    return out


def has_placeholder(value):
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


def usable_event(item):
    if not isinstance(item, dict):
        return False
    if item.get("type") == "source":
        return True
    title = clean_text(item.get("title") or item.get("what") or item.get("name") or item.get("event"))
    url = clean_text(item.get("url") or item.get("link") or item.get("href"))
    if has_placeholder(item):
        return False
    if not title and not url:
        return False
    return True


def sanitize_local_events_payload(data):
    if not isinstance(data, dict):
        return {"results": []}

    cleaned = sanitize_dict(data)

    for field in ("results", "items", "events"):
        rows = cleaned.get(field)
        if isinstance(rows, list):
            cleaned[field] = [item for item in rows if usable_event(item)]

    if isinstance(cleaned.get("results"), list):
        cleaned["count"] = len(cleaned["results"])
        cleaned["items"] = cleaned["results"]
    elif isinstance(cleaned.get("items"), list):
        cleaned["count"] = len(cleaned["items"])
        cleaned["results"] = cleaned["items"]

    settings = cleaned.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["api_sanitizes_template_placeholders"] = True

    return cleaned


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def read_local_events():
    return sanitize_local_events_payload(read_json(BASE / "local_event_search_results.json", {"results": []}))


def write_local_events(data):
    cleaned = sanitize_local_events_payload(data)
    (BASE / "local_event_search_results.json").write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cleaned


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

    def body_json(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/market-config":
            return self.send_json(read_json(BASE / "market_config.json", {
                "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
            }))

        if path == "/api/local-events/search":
            return self.send_json(read_local_events())

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/market-config":
            try:
                body = self.body_json()
                raw = body.get("symbols", [])
                if not isinstance(raw, list):
                    raise ValueError("symbols must be list")

                symbols = []
                for x in raw:
                    s = str(x).strip().upper()
                    if s and s not in symbols:
                        symbols.append(s)

                symbols = symbols[:12]
                if not symbols:
                    raise ValueError("empty symbols")

                payload = {
                    "symbols": symbols,
                    "updated_at": now()
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
                    timeout=60,
                )
                return self.send_json({
                    "ok": p.returncode == 0,
                    "returncode": p.returncode,
                    "stdout": p.stdout[-2000:],
                    "stderr": p.stderr[-2000:],
                    "market": read_json(BASE / "market.json", {})
                }, 200 if p.returncode == 0 else 500)
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 500)

        if path == "/api/local-events/search":
            try:
                body = self.body_json()
                location = str(body.get("location") or "Punggol Singapore")
                p = subprocess.run(
                    [sys.executable, str(BASE / "search_local_events.py"), location],
                    cwd=str(BASE),
                    text=True,
                    capture_output=True,
                    timeout=90,
                )
                data = write_local_events(read_json(BASE / "local_event_search_results.json", {"results": []}))
                data["ok"] = p.returncode == 0
                data["stdout"] = p.stdout[-1000:]
                data["stderr"] = p.stderr[-1000:]
                return self.send_json(data, 200 if p.returncode == 0 else 500)
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 500)

        return self.send_json({"ok": False, "error": "not found"}, 404)


def main():
    print(f"InfoScreen API server on 0.0.0.0:8765 from {BASE}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8765), Handler).serve_forever()


if __name__ == "__main__":
    main()
