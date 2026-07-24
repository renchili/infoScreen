#!/usr/bin/env python3
from __future__ import annotations

from local_events_runtime.http1_browser import apply as apply_http1_browser

apply_http1_browser()

from jobs.local_event_search import main


if __name__ == "__main__":
    raise SystemExit(main())
