#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$REPO_ROOT"

if ! command -v node >/dev/null 2>&1; then
  echo "node is required for JavaScript syntax checks" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

while IFS= read -r -d '' file; do
  node --check "$file"
done < <(git ls-files -z -- '*.js')

html_index=0
while IFS= read -r -d '' html; do
  html_index=$((html_index + 1))
  python3 scripts/ci/extract_inline_js.py \
    "$html" \
    "$TEMP_DIR/inline-js-$html_index"
done < <(git ls-files -z -- '*.html')

while IFS= read -r -d '' file; do
  node --check "$file"
done < <(find "$TEMP_DIR" -type f -name '*.js' -print0)

echo "PASSED JavaScript syntax"
