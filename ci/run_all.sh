#!/usr/bin/env bash
set -Eeuo pipefail

echo "==> python compile"
python -m compileall -q .

echo "==> ruff critical errors"
ruff check --select E9,F63,F7,F82 .

echo "==> pytest"
pytest -q

echo "==> inline/external javascript syntax"
python tests/check_javascript_syntax.py
