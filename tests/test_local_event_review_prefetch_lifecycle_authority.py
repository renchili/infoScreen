from __future__ import annotations

import sys
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import review_detail_prefetch_authority as prefetch  # noqa: E402
from local_events_runtime import review_prefetch_lifecycle_authority as lifecycle  # noqa: E402


class FakeContext:
    pass


def test_prefetch_uses_admitted_card_markers_before_source_selectors() -> None:
    script = lifecycle.ADMITTED_DETAIL_URLS_JS

    assert 'document.querySelectorAll("[data-infoscreen-card-id]")' in script
    assert "if (marked.length)" in script
    assert "marked.forEach(addRoot)" in script
    assert "} else {" in script
    assert "args.selectors || []" in script


def test_consumed_prefetch_entry_releases_seen_and_page_state() -> None:
    prefetch._STATES.clear()
    context = FakeContext()
    state = prefetch._state(context)
    page = object()
    key = prefetch._canonical_url("https://www.acm.nhb.gov.sg/whats-on/exhibitions/pagoda-odyssey")
    entry = SimpleNamespace(page=page, requested_url=key)
    state.entries[key] = entry
    state.seen.add(key)
    state.page_ids.add(id(page))

    result = lifecycle.take_prefetched(context, key)

    assert result is entry
    assert key not in state.entries
    assert key not in state.seen
    assert id(page) not in state.page_ids


def test_prefetch_lifecycle_is_installed_before_listing_and_pagination_rules() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    prefetch_apply = bootstrap.index("apply_review_detail_prefetch_authority()")
    lifecycle_apply = bootstrap.index("apply_review_prefetch_lifecycle_authority()")
    dynamic_apply = bootstrap.index("apply_dynamic_listing_authority()")
    pagination_apply = bootstrap.index("apply_listing_pagination_authority()")

    assert prefetch_apply < lifecycle_apply < dynamic_apply < pagination_apply
