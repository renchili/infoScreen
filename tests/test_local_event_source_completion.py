from __future__ import annotations

import sys

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from jobs.local_event_search import annotate_source_completion  # noqa: E402

pytestmark = pytest.mark.backend


def test_multi_listing_debug_rows_count_as_one_completed_source() -> None:
    payload = annotate_source_completion(
        {
            "source_count": 2,
            "debug_by_source": [
                {
                    "source": "Esplanade",
                    "listing_urls": ["https://example.test/legacy-list"],
                    "listing_fetched": 1,
                    "complete": True,
                },
                {
                    "source_id": "esplanade",
                    "source": "Esplanade",
                    "listing_urls": ["https://example.test/studio-list"],
                    "listing_fetched": 1,
                    "complete": True,
                },
                {
                    "source_id": "onepa",
                    "source": "onePA",
                    "listing_urls": ["https://example.test/events"],
                    "listing_fetched": 1,
                    "complete": True,
                },
            ],
        }
    )

    assert payload["source_count"] == 2
    assert payload["completed_source_count"] == 2
    assert payload["incomplete_source_count"] == 0
    assert payload["source_status_counts"] == {"complete": 2}
    assert payload["partial"] is False


def test_one_failed_listing_makes_its_source_partial_without_overcounting() -> None:
    payload = annotate_source_completion(
        {
            "source_count": 2,
            "debug_by_source": [
                {
                    "source": "Esplanade",
                    "listing_urls": ["https://example.test/legacy-list"],
                    "listing_fetched": 1,
                    "complete": True,
                },
                {
                    "source_id": "esplanade",
                    "source": "Esplanade",
                    "listing_urls": ["https://example.test/studio-list"],
                    "listing_fetched": 0,
                    "complete": False,
                    "reason_counts": {"browser_failure": 1},
                },
                {
                    "source_id": "onepa",
                    "source": "onePA",
                    "listing_urls": ["https://example.test/events"],
                    "listing_fetched": 1,
                    "complete": True,
                },
            ],
        }
    )

    assert payload["completed_source_count"] == 1
    assert payload["incomplete_source_count"] == 1
    assert payload["source_status_counts"] == {"partial": 1, "complete": 1}
    assert payload["partial"] is True


def test_existing_partial_flag_is_not_cleared_by_complete_debug_rows() -> None:
    payload = annotate_source_completion(
        {
            "source_count": 1,
            "partial": True,
            "debug_by_source": [
                {
                    "source_id": "esplanade",
                    "listing_urls": ["https://example.test/list"],
                    "listing_fetched": 1,
                    "complete": True,
                }
            ],
        }
    )

    assert payload["completed_source_count"] == 1
    assert payload["partial"] is True
