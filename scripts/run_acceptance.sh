#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

ARTIFACT_DIR="${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}"
rm -rf "$ARTIFACT_DIR"
mkdir -p "$ARTIFACT_DIR"
SUMMARY="$ARTIFACT_DIR/summary.md"
FAILURES=0
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

{
  echo "# InfoScreen Acceptance Summary"
  echo
  echo "- repository: $(basename "$ROOT")"
  echo "- commit: $(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "- branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "- artifact_dir: $ARTIFACT_DIR"
  echo
  echo "## Checks"
} > "$SUMMARY"

run_step() {
  local name="$1"
  shift
  local log_file="$ARTIFACT_DIR/${name}.log"
  echo "[RUN] $name"
  if "$@" >"$log_file" 2>&1; then
    echo "- PASS: $name" >> "$SUMMARY"
    echo "[PASS] $name"
  else
    echo "- FAIL: $name — see ${name}.log" >> "$SUMMARY"
    echo "[FAIL] $name"
    cat "$log_file" >&2 || true
    FAILURES=$((FAILURES + 1))
  fi
}

run_step metadata_json python3 -m json.tool metadata.json

run_step acceptance_skill_present bash -lc 'test -f skills/full-project-acceptance-hard-gates'

run_step agent_docs_project_identity bash -lc '! grep -R "IronPage\|\.chatgpt/skills/ironpage" AGENT.md AGENTS.md'

run_step python_compile python3 -m compileall -q surface

run_step openapi_generation bash -lc 'python3 - <<"PY"
import json
from pathlib import Path
from surface.openapi_spec import build_openapi
payload = build_openapi()
Path("$ARTIFACT_DIR/openapi.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY'

run_step frontend_asset_contract bash -lc 'grep -q "assets/js/dashboard.js" surface/web/index.html && grep -q "assets/js/local_event_card.js" surface/web/index.html && grep -q "surface/.env/photos" surface/web/index.html && test -z "$(find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print -quit)"'

run_step root_hygiene bash -lc 'python3 - <<"PY"
import subprocess
import sys

allowed_files = {"README.md", "AGENTS.md", "AGENT.md", "metadata.json", ".gitignore"}
allowed_dirs = {".githooks", ".github", "docs", "skills", "surface", "deploy", "mac", "scripts"}
blocked_prefixes = ("surface/.env/", ".env/", "logs/", ".review_delete/", "photo/", "photos/", "public_photos/", "chatgpt-ui-once/")
blocked_names = {"mac/local.env", "mac/schedule.json"}
blocked_suffixes = (".pyc", ".tmp", ".log", ".bak", ".backup", ".DS_Store")
paths = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
bad = []
for path in paths:
    if path in blocked_names or path.startswith(blocked_prefixes) or path.endswith(blocked_suffixes):
        bad.append(f"runtime/cache tracked: {path}")
        continue
    if "/" not in path:
        if path not in allowed_files:
            bad.append(f"bad root file: {path}")
        continue
    top = path.split("/", 1)[0]
    if top not in allowed_dirs:
        bad.append(f"bad top-level dir: {path}")
if bad:
    print("\n".join(bad))
    sys.exit(1)
PY'

run_step precommit_no_staged_input bash -lc 'chmod +x .githooks/pre-commit && git diff --cached --name-only | .githooks/pre-commit'

if [ "${ACCEPTANCE_START_SERVER:-0}" = "1" ]; then
  echo "[RUN] start_server"
  python3 surface/serve_infoscreen.py >"$ARTIFACT_DIR/server.log" 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8765/ >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  ACCEPTANCE_HTTP=1
fi

if [ "${ACCEPTANCE_HTTP:-0}" = "1" ]; then
  run_step http_dashboard bash -lc 'curl -fsS http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"'
  run_step http_openapi bash -lc 'curl -fsS http://127.0.0.1:8765/openapi.json > "$ARTIFACT_DIR/http-openapi.json"'
else
  echo "- SKIP: http_dashboard — set ACCEPTANCE_START_SERVER=1 or ACCEPTANCE_HTTP=1" >> "$SUMMARY"
  echo "- SKIP: http_openapi — set ACCEPTANCE_START_SERVER=1 or ACCEPTANCE_HTTP=1" >> "$SUMMARY"
fi

{
  echo
  echo "## Result"
  if [ "$FAILURES" -eq 0 ]; then
    echo "PASS"
  else
    echo "FAIL: $FAILURES check(s) failed"
  fi
} >> "$SUMMARY"

cat "$SUMMARY"

if [ "$FAILURES" -ne 0 ]; then
  exit 1
fi
