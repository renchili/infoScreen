#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import local_events_engine as engine

SURFACE_DIR = Path(__file__).resolve().parent
ENV_DIR = SURFACE_DIR / ".env"
CONF_DIR = SURFACE_DIR / "conf"

engine.APP_ROOT = SURFACE_DIR
engine.REGISTRY = CONF_DIR / "official_source_registry.json"
engine.OUT = ENV_DIR / "local_event_search_results.json"


def _patched_primary_block(page: str, title: str):
    """Pick the local detail block that contains primary event metadata.

    NHB pages repeat titles in head/nav/related cards. Some detail pages do not
    repeat the full title in the visible body at all, but still put the primary
    date/time/venue near the top of the detail body. This keeps extraction local:
    prefer a title occurrence with nearby date evidence, otherwise anchor on the
    first strong date row after the navigation area.
    """
    lines = engine.visible_lines(page)
    if not lines:
        return [], {"primary_block_found": False, "reason": "no_visible_lines"}

    tokens = engine.title_tokens(title)
    starts = []
    for index, line in enumerate(lines):
        low = line.lower()
        if any(token in low for token in tokens):
            starts.append(index)

    def make_block(start: int, limit: int = 140):
        block = []
        for line in lines[start:]:
            if block and engine.BOUNDARY_RE.search(line):
                break
            block.append(line)
            if len(block) >= limit:
                break
        return block

    def date_strength(line: str) -> int:
        if not (engine.DATE_SEARCH_RE.search(line) or engine.OPEN_START_RE.search(line)):
            return 0
        if engine.BAD_DATE_RE.search(line):
            return -50
        score = 20
        if engine.FULL_RANGE_RE.search(line) or engine.END_YEAR_RANGE_RE.search(line):
            score += 80
        if engine.OPEN_START_RE.search(line):
            score += 60
        if engine.SAME_MONTH_RANGE_RE.search(line):
            score += 35
        return score

    def score_block(block):
        score = 0
        for offset, line in enumerate(block[:80]):
            strength = date_strength(line)
            if strength:
                score += strength + 120 - min(offset, 80)
            window = " ".join(block[max(0, offset - 2): offset + 5])
            if engine.TIME_RE.search(window):
                score += 8
            if engine.VENUE_RE.search(window):
                score += 8
        return score

    choices = []
    for start in starts:
        block = make_block(start)
        choices.append((score_block(block), start, block, "title_anchor"))

    # Fallback for official detail pages whose visible body omits the full title.
    # Start a small block just before the first strong primary date row, instead
    # of accepting the full page or nav block.
    for index, line in enumerate(lines):
        strength = date_strength(line)
        if strength <= 0:
            continue
        low_context = " ".join(lines[max(0, index - 12): index + 8]).lower()
        if any(bad in low_context for bad in ("last updated", "newsletter", "keep up to date", "privacy statement", "terms of use")):
            continue
        start = max(0, index - 12)
        block = make_block(start, 90)
        choices.append((score_block(block) + strength, start, block, "date_anchor"))

    if not choices:
        block = make_block(0, 90)
        return block, {"primary_block_found": bool(block), "block_start": 0, "block_score": 0, "block_anchor": "fallback_zero", "block_preview": block[:12]}

    choices.sort(key=lambda item: (-item[0], item[1]))
    score, start, block, anchor = choices[0]
    return block, {
        "primary_block_found": bool(block),
        "block_start": start,
        "block_score": score,
        "block_anchor": anchor,
        "block_preview": block[:12],
    }


engine.primary_block = _patched_primary_block


def main() -> int:
    ENV_DIR.mkdir(exist_ok=True)
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
