#!/usr/bin/env python3
"""
Disabled placeholder.

The v21 crawler direction is intentionally not used because it confused parser
failure with source/data invalidity. The crawler must be replaced by a field
locator that separates parser_error from expired/invalid events.
"""

raise SystemExit(
    "search_local_events.py is disabled: replace with field-locator crawler; "
    "do not classify parser failure as invalid source data."
)
