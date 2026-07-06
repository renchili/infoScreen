#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

ARTIFACT_DIR="${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}"
RUNTIME_ENV="$ARTIFACT_DIR/runtime_env"
export ARTIFACT_DIR
export INFOSCREEN_ENV_DIR="$RUNTIME_ENV"

mkdir -p "$ARTIFACT_DIR" "$RUNTIME_ENV" "$RUNTIME_ENV/public_photos"
SUMMARY="$ARTIFACT_DIR/summary.md"
: > "$SUMMARY"
FAILURES=0

log_step() {
  local name="$1"
  shift
  local log_file="$ARTIFACT_DIR/${name}.log"
  echo "[RUN] $name"
  if "$@" >"$log_file" 2>&1; then
    echo "PASS $name" | tee -a "$SUMMARY"
  else
    echo "FAIL $name" | tee -a "$SUMMARY"
    cat "$log_file" >&2 || true
    FAILURES=$((FAILURES + 1))
  fi
}

log_step seed_runtime_data python3 -c 'import os, shutil; from pathlib import Path; root=Path.cwd(); out=Path(os.environ["INFOSCREEN_ENV_DIR"]); [shutil.copy2(p, out/p.name) for p in (root/"tests/fixtures/runtime_data").glob("*.json")]; (out/"public_photos"/"fixture-photo.txt").write_text("fixture photo bytes\n", encoding="utf-8")'
log_step repo_hygiene python3 scripts/ci/check_repo.py --suite all --scope repository
log_step metadata_json python3 -m json.tool metadata.json
log_step python_compile python3 -m compileall -q surface tests scripts
log_step openapi_generation python3 -c 'import json, os; from pathlib import Path; from surface.openapi_spec import build_openapi; Path(os.environ["ARTIFACT_DIR"], "openapi.json").write_text(json.dumps(build_openapi(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")'
log_step shell_syntax bash -n scripts/run_full_ci_tests.sh
log_step pytest python3 -m pytest --junitxml "$ARTIFACT_DIR/pytest-junit.xml"

python3 -c 'import json, os, subprocess; from pathlib import Path; d=Path(os.environ["ARTIFACT_DIR"]); summary=d/"summary.md"; report={"commit": subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip(), "artifact_dir": str(d), "runtime_env": os.environ["INFOSCREEN_ENV_DIR"], "logs": sorted(str(p) for p in d.glob("*.log")), "junit": str(d/"pytest-junit.xml"), "openapi": str(d/"openapi.json"), "summary": str(summary), "summary_text": summary.read_text(encoding="utf-8")}; (d/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")'

find "$ARTIFACT_DIR" -maxdepth 2 -type f | sort
cat "$SUMMARY"
if [ "$FAILURES" -ne 0 ]; then
  exit 1
fi
