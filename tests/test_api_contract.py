from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8765"


def wait_for_http() -> None:
    deadline = time.time() + 8

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)

    raise AssertionError("serve_infoscreen.py did not start on port 8765")


def request_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=3) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode("utf-8"))


def test_http_server_contract_for_static_and_local_events() -> None:
    cache = Path("local_event_search_results.json")
    old = cache.read_text(encoding="utf-8") if cache.exists() else None

    fixture = {
        "location": "Punggol Singapore",
        "results": [
            {
                "title": "Sample local event",
                "when": "CHECK DATE",
                "source_name": "fixture",
                "url": "https://example.invalid/event",
            }
        ],
    }

    cache.write_text(json.dumps(fixture), encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, "serve_infoscreen.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        wait_for_http()

        with urllib.request.urlopen(BASE + "/", timeout=3) as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")

        data = request_json("/api/local-events/search")
        assert isinstance(data.get("results"), list)
        assert data["results"][0]["title"] == "Sample local event"

        source = Path("serve_infoscreen.py").read_text(encoding="utf-8")
        assert "/api/local-events/search" in source
        assert "do_POST" in source
        assert "search_local_events.py" in source

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

        if old is None:
            cache.unlink(missing_ok=True)
        else:
            cache.write_text(old, encoding="utf-8")
