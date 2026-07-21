from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .event_review import (
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
    canonical_url,
    stable_id,
    utc_now,
)

MANUAL_LINK_TEXT = "Manually added by operator"


class ManualListingRequest(BaseModel):
    """Validated operator request for one official Event listing page."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=120)
    url: HttpUrl


def _host_allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    allowed = [
        str(value).lower().removeprefix("www.")
        for value in source.get("allowed_domains") or []
        if str(value).strip()
    ]
    return bool(
        host
        and any(host == domain or host.endswith("." + domain) for domain in allowed)
    )


def add_manual_listing(
    store: EventReviewStore,
    request: ManualListingRequest,
) -> ReviewState:
    """Add or reset one operator-supplied list page inside review state.

    Manual pages remain review candidates. They are not written into committed source
    configuration and do not become collection inputs until the operator confirms them.
    """

    source = store.source(request.source_id.strip())
    source_id = str(source.get("id") or "").strip()
    source_name = str(source.get("name") or source_id).strip()
    url = canonical_url(str(request.url))
    if not _host_allowed(url, source):
        raise ValueError("listing URL is outside the institution allow-list")

    state = store.load()
    candidate_id = stable_id(source_id, url)
    existing = next(
        (item for item in state.listing_pages if item.candidate_id == candidate_id),
        None,
    )

    if existing is None:
        state.listing_pages.append(
            ListingPageCandidate(
                candidate_id=candidate_id,
                source_id=source_id,
                source_name=source_name,
                url=url,
                origin="discovered",
                link_text=MANUAL_LINK_TEXT,
                decision="pending",
                discovered_at=utc_now(),
            )
        )
    else:
        existing.decision = "pending"
        existing.reviewed_at = None
        if existing.origin != "configured":
            existing.link_text = MANUAL_LINK_TEXT
            existing.discovered_at = utc_now()

    state.listing_pages = sorted(
        state.listing_pages,
        key=lambda item: (item.source_name.casefold(), item.url),
    )
    return store.save(state)


__all__ = ["ManualListingRequest", "add_manual_listing"]
