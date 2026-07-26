#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# The supported installer generates the LaunchAgent from the current checkout and
# machine-local arguments. No committed plist may contain a developer home path.
exec bash "$REPO_DIR/mac/scripts/setup-schedule-sync.sh" "$@"
