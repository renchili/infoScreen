#!/usr/bin/env bash
set -Eeuo pipefail

echo "==> mac lightweight check"
python3 -m compileall -q .

echo "==> tracked runtime pollution"
python3 - <<'PY'
import subprocess

runtime = {
    "schedule.json",
    "weather.json",
    "market.json",
    "event_stream.json",
    "local_event_search_results.json",
    "photos.json",
    "index2.html",
}

tracked = set(
    subprocess.check_output(["git", "ls-files"], text=True).splitlines()
)

bad = sorted(runtime & tracked)
if bad:
    raise SystemExit("runtime files tracked: " + ", ".join(bad))

print("runtime pollution check OK")
PY

echo "Mac lightweight check OK"
