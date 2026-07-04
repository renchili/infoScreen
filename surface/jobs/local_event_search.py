#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

SURFACE_DIR = Path(__file__).resolve().parents[1]


def main(argv=None):
    import sys
    sys.path.insert(0, str(SURFACE_DIR))
    from search_local_events import main as legacy_main
    return legacy_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
