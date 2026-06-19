#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$REPO_ROOT"

while IFS= read -r -d '' file; do
  bash -n "$file"
done < <(git ls-files -z -- '*.sh')

echo "PASSED shell syntax"
