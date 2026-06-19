#!/usr/bin/env bash
set -Eeuo pipefail

# GitHub Actions mounts the checkout into Docker as /repo. The directory
# owner can differ from the container user, so Git refuses commands like
# `git ls-files` unless the mounted repo is explicitly trusted.
git config --global --add safe.directory /repo
git config --global --add safe.directory "$(pwd)"

echo "==> python compile"
python -m compileall -q .

echo "==> ruff critical errors"
ruff check --select E9,F63,F7,F82 .

echo "==> pytest"
pytest -q

echo "==> inline/external javascript syntax"
python tests/check_javascript_syntax.py
