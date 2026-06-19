#!/usr/bin/env bash
set -u
set -o pipefail

main() {
  local repo_root base_ref suite

  repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "Run this command from inside the Git repository." >&2
    return 1
  }

  cd "$repo_root" || return 1
  base_ref="${1:-origin/main}"

  if git rev-parse --verify --quiet "$base_ref" >/dev/null; then
    :
  else
    echo "Base ref not found: $base_ref" >&2
    echo "Run: git fetch origin main" >&2
    return 1
  fi

  for suite in paths content structure python; do
    printf '\n==> %s\n' "$suite"
    python3 scripts/ci/check_repo.py \
      --suite "$suite" \
      --scope changed \
      --base "$base_ref" \
      --head HEAD \
      --include-working-tree || return 1
  done

  printf '\n==> shell\n'
  bash scripts/ci/check_shell_syntax.sh || return 1

  printf '\n==> javascript\n'
  bash scripts/ci/check_javascript_syntax.sh || return 1

  printf '\nPRE-PR TESTS PASSED\n'
}

main "$@"
