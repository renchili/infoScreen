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
    """Pick the title occurrence whose following block contains event metadata.

    The engine's original primary_block uses the first visible title occurrence.
    NHB pages can repeat the title in head/nav before the real detail body, so
    that block misses the nearby date rows. This version still anchors on the
    page title, but chooses the title occurrence with nearby date/time/venue
    evidence instead of scanning the whole page as one text blob.
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

    if not starts:
        starts = [0]

    def make_block(start: int):
        block = []
        for line in lines[start:]:
            if block and engine.BOUNDARY_RE.search(line):
                break
            block.append(line)
            if len(block) >= 120:
                break
        return block

    def score_block(block):
        score = 0
        for offset, line in enumerate(block[:55]):
            window = " ".join(block[max(0, offset - 2): offset + 5])
            if engine.DATE_SEARCH_RE.search(line) or engine.OPEN_START_RE.search(line):
                score += 120 - min(offset, 60)
                if engine.FULL_RANGE_RE.search(line) or engine.END_YEAR_RANGE_RE.search(line):
                    score += 50
                if engine.OPEN_START_RE.search(line):
                    score += 40
                if engine.BAD_DATE_RE.search(line):
                    score -= 80
            if engine.TIME_RE.search(window):
                score += 8
            if engine.VENUE_RE.search(window):
                score += 8
        return score

    choices = []
    for start in starts:
        block = make_block(start)
        choices.append((score_block(block), start, block))

    choices.sort(key=lambda item: (-item[0], item[1]))
    score, start, block = choices[0]
    return block, {
        "primary_block_found": bool(block),
        "block_start": start,
        "block_score": score,
        "block_preview": block[:12],
    }


engine.primary_block = _patched_primary_block


def main() -> int:
    ENV_DIR.mkdir(exist_ok=True)
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
