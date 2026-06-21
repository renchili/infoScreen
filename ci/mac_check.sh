#!/usr/bin/env bash
set -Eeuo pipefail

echo "==> mac lightweight check"
python3 -m compileall -q .

echo "==> changed runtime pollution"
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

def changed_files() -> set[str]:
    for args in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "origin/main", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
    ):
        result = subprocess.run(args, text=True, capture_output=True)
        if result.returncode == 0:
            return set(result.stdout.splitlines())

    raise SystemExit("unable to calculate changed files")

bad = sorted(runtime & changed_files())
if bad:
    raise SystemExit("runtime files changed in PR: " + ", ".join(bad))

print("runtime pollution check OK")
PY

echo "Mac lightweight check OK"
