from __future__ import annotations

from typing import Any

from . import extract as _extract
from . import review_publish_authority as _publisher

_APPLIED = False
_BASE_REVIEW_EVENT = None


def _review_summary(value: object) -> str:
    """Keep concise operator-reviewed narrative while rejecting operational copy."""

    from . import detail_summary_authority as detail

    text = _extract.clean(value)
    if not text:
        return ""

    narrative = detail.useful_event_summary(text)
    if narrative:
        return narrative

    # Detail-page discovery needs a minimum length to avoid labels and fragments.
    # A human-confirmed Review summary may be concise, but must still reject the
    # same CTA, terms, contact, registration, safety, and shell patterns.
    if len(text) < 8 or len(text) > 500:
        return ""
    if detail._OPERATION_BOUNDARY_RE.search(text):
        return ""
    if detail._CTA_RE.search(text) or detail._SHELL_RE.search(text):
        return ""
    return text


def _review_event(candidate: Any) -> dict[str, Any]:
    """Remove CTA, terms, contact, registration, and safety text before publish."""

    event = dict(_BASE_REVIEW_EVENT(candidate))
    event["summary"] = _review_summary(event.get("summary"))
    return event


def apply() -> None:
    """Make narrative detail text the only Review-authoritative summary."""

    global _APPLIED, _BASE_REVIEW_EVENT
    if _APPLIED:
        # Test modules and later authority composition may temporarily restore the
        # publisher's base function. Re-applying the authority must restore the
        # product invariant without wrapping the function a second time.
        _publisher._review_event = _review_event
        return

    # The canonical job calls this authority directly. Apply the detail authority
    # here as well so scheduled, HTTP, Studio, and direct job paths use one rule.
    from .detail_summary_authority import apply as apply_detail_summary_authority

    apply_detail_summary_authority()
    _BASE_REVIEW_EVENT = _publisher._review_event
    _publisher._review_event = _review_event

    # A renderer crash poisons a Playwright Page permanently. Review previously retried
    # the same dead Page, so one ACM listing crash produced a false zero-candidate run.
    # Wrap the final browser launcher before the isolated worker starts collection.
    from .review_listing_page_recovery_authority import (
        apply as apply_review_listing_page_recovery_authority,
    )

    apply_review_listing_page_recovery_authority()

    # event_review_diagnostics has now installed the final full-fidelity Review
    # collector. Wrap that final function in a killable child process before the HTTP
    # server imports it by value. Worker processes set the child marker and therefore
    # execute the real collector directly instead of recursively spawning workers.
    from .review_collection_timeout_authority import (
        apply as apply_review_collection_timeout_authority,
    )

    apply_review_collection_timeout_authority()
    _APPLIED = True


__all__ = ["apply"]
