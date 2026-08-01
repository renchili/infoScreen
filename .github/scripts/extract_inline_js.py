#!/usr/bin/env python3
import re
import shutil
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: extract_inline_js.py <index.html> <output-dir>")

html_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])

html = html_path.read_text(encoding="utf-8")
scripts = re.findall(
    r"<script\b[^>]*>(.*?)</script\s*>",
    html,
    flags=re.IGNORECASE | re.DOTALL,
)

if output_dir.exists():
    shutil.rmtree(output_dir)

output_dir.mkdir(parents=True, exist_ok=True)

written = 0
for index, script in enumerate(scripts, start=1):
    if not script.strip():
        continue

    target = output_dir / f"inline-{index}.js"
    target.write_text(script, encoding="utf-8")
    written += 1

print(f"extracted {written} inline JavaScript block(s)")
