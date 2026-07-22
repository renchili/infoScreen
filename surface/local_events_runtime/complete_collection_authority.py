from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import extract as _extract
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_RENDER = None

# The configured inventory contains 18 institutions and some official pages expose
# many cards whose detail pages may each take close to a minute. These are coverage
# floors, not performance targets: runtime configuration may raise them but must not
# silently reduce the supported collection scope.
MIN_TOTAL_SECONDS = 7200.0
MIN_SOURCE_SECONDS = 1200.0
MIN_SOURCE_CONCURRENCY = 4
MIN_EVENTS_PER_SOURCE = 180
MIN_TOTAL_EVENTS = 180
MIN_LISTING_PAGES = 20
MIN_LOAD_MORE_ROUNDS = 24
MIN_NAV_TIMEOUT_MS = 25000
MIN_DOM_TIMEOUT_MS = 25000
MIN_DETAIL_TIMEOUT_MS = 60000
MIN_DETAIL_LIMIT = 180


def apply() -> None:
    """Lift import-time collector limits so every configured source can run.

    Local Events modules read environment values during import. Both the HTTP
    server and the compatibility wrapper import the runtime package before the job
    module, so relying on job-level ``setdefault`` calls can leave stale, smaller
    limits active. This authority updates the live module globals that the
    collector actually reads and expands the card-render limit to the supported
    per-source Event budget.
    """

    global _APPLIED, _BASE_RENDER
    if _APPLIED:
        return

    _extract.MAX_SECONDS = max(float(_extract.MAX_SECONDS), MIN_TOTAL_SECONDS)
    _extract.SOURCE_TIMEOUT_SECONDS = max(
        float(_extract.SOURCE_TIMEOUT_SECONDS),
        MIN_SOURCE_SECONDS,
    )
    _extract.SOURCE_CONCURRENCY = max(
        int(_extract.SOURCE_CONCURRENCY),
        MIN_SOURCE_CONCURRENCY,
    )
    _extract.MAX_EVENTS_PER_SOURCE = max(
        int(_extract.MAX_EVENTS_PER_SOURCE),
        MIN_EVENTS_PER_SOURCE,
    )
    _extract.MAX_TOTAL_EVENTS = max(
        int(_extract.MAX_TOTAL_EVENTS),
        MIN_TOTAL_EVENTS,
    )

    _browser.MAX_LISTING_PAGES = max(
        int(_browser.MAX_LISTING_PAGES),
        MIN_LISTING_PAGES,
    )
    _browser.LOAD_MORE_ROUNDS = max(
        int(_browser.LOAD_MORE_ROUNDS),
        MIN_LOAD_MORE_ROUNDS,
    )
    _browser.NAV_TIMEOUT_MS = max(
        int(_browser.NAV_TIMEOUT_MS),
        MIN_NAV_TIMEOUT_MS,
    )
    _browser.DOM_TIMEOUT_MS = max(
        int(_browser.DOM_TIMEOUT_MS),
        MIN_DOM_TIMEOUT_MS,
    )

    _source_overrides.DETAIL_LIMIT = max(
        int(_source_overrides.DETAIL_LIMIT),
        MIN_DETAIL_LIMIT,
    )
    _source_overrides.DETAIL_TIMEOUT_MS = max(
        int(_source_overrides.DETAIL_TIMEOUT_MS),
        MIN_DETAIL_TIMEOUT_MS,
    )

    _BASE_RENDER = _extract.render_listing_cards

    def render_listing_cards(
        source: dict[str, Any],
        url: str,
        debug_dir,
        max_cards: int = 60,
    ):
        return _BASE_RENDER(
            source,
            url,
            debug_dir,
            max_cards=max(int(max_cards), int(_extract.MAX_EVENTS_PER_SOURCE)),
        )

    _extract.render_listing_cards = render_listing_cards
    _APPLIED = True


__all__ = ["apply"]
