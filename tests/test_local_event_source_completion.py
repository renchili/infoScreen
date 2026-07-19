from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from jobs import local_event_search  # noqa: E402

pytestmark = pytest.mark.backend


def test_multi_listing_debug_rows_count_as_one_completed_source() -> None:
    payload = local_event_search.annotate_source_completion(
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
    payload = local_event_search.annotate_source_completion(
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
    payload = local_event_search.annotate_source_completion(
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


def test_structured_first_cache_keeps_missing_policy_but_rejects_wrong_policy() -> None:
    cached = local_event_search.verified_previous_payload(
        {
            "extractor": "structured-first-v49-source-order",
            "results": [
                {"title": "Displayable legacy row", "url": "https://example.test/events/one"},
                {
                    "title": "Published Studio row",
                    "url": "https://example.test/events/two",
                    "candidate_policy": "official-listing-authority-v1",
                },
                {
                    "title": "Obsolete policy row",
                    "url": "https://example.test/events/three",
                    "candidate_policy": "canonical-detail-evidence-v1",
                },
            ],
        }
    )

    assert [item["title"] for item in cached["results"]] == [
        "Displayable legacy row",
        "Published Studio row",
    ]
    assert cached["legacy_unverified_removed"] == 1
    assert cached["cache_policy"] == "structured-first-compatible-v1"


def test_non_structured_cache_does_not_keep_missing_policy() -> None:
    cached = local_event_search.verified_previous_payload(
        {
            "extractor": "legacy-v1",
            "results": [
                {"title": "Unverified", "url": "https://example.test/events/one"},
                {
                    "title": "Verified",
                    "url": "https://example.test/events/two",
                    "candidate_policy": "official-listing-authority-v1",
                },
            ],
        }
    )

    assert [item["title"] for item in cached["results"]] == ["Verified"]
    assert cached["cache_policy"] == "official-listing-authority-v1"


def test_partial_write_keeps_larger_structured_first_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "local_event_search_results.json"
    partial = tmp_path / "local_event_search_results.partial.json"
    out.write_text(
        json.dumps(
            {
                "extractor": "structured-first-v49-source-order",
                "results": [
                    {
                        "title": "Previous current event",
                        "when": "2099-07-19",
                        "start_date": "2099-07-19",
                        "where": "Official venue",
                        "url": "https://example.test/events/previous-current-event",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(local_event_search, "OUT", out)
    monkeypatch.setattr(local_event_search, "PARTIAL_OUT", partial)

    local_event_search.write_payload(
        {
            "extractor": "structured-first-v49-source-order",
            "source_count": 1,
            "partial": True,
            "results": [],
            "debug_by_source": [
                {
                    "source": "Esplanade",
                    "listing_urls": ["https://example.test/list"],
                    "listing_fetched": 0,
                    "complete": False,
                    "reason_counts": {"browser_failure": 1},
                }
            ],
        }
    )

    primary = json.loads(out.read_text(encoding="utf-8"))
    diagnostic = json.loads(partial.read_text(encoding="utf-8"))
    assert [item["title"] for item in primary["results"]] == ["Previous current event"]
    assert diagnostic["write_policy"] == "kept_previous_verified_result"
    assert diagnostic["previous_cache_policy"] == "structured-first-compatible-v1"
