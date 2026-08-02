from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import listing_page_archive_authority as authority  # noqa: E402
from local_events_runtime import listing_page_policy as policy  # noqa: E402
from local_events_runtime.event_review import EventReviewStore  # noqa: E402
from local_events_runtime.manual_listing import (  # noqa: E402
    ManualListingRequest,
    add_manual_listing,
)


def test_archive_url_and_link_text_are_not_current_listing_pages() -> None:
    assert not policy.is_current_listing_page(
        "https://www.marinabaysands.com/museum/about-us/exhibition-archive.html",
        "Archive Archive",
    )
    assert not policy.is_current_listing_page(
        "https://example.com/museum/past-exhibitions",
        "Exhibitions",
    )
    assert not policy.is_current_listing_page(
        "https://example.com/museum/exhibitions",
        "Exhibition archive",
    )
    assert policy.is_current_listing_page(
        "https://www.marinabaysands.com/museum/whats-on.html",
        "What's On",
    )


def test_studio_payload_hides_archive_page_and_its_event(monkeypatch) -> None:
    archive = (
        "https://www.marinabaysands.com/museum/about-us/"
        "exhibition-archive.html"
    )
    current = "https://www.marinabaysands.com/museum/whats-on.html"
    monkeypatch.setattr(
        authority,
        "_BASE_STATE_PAYLOAD",
        lambda store: {
            "ok": True,
            "listing_pages": [
                {"url": archive, "link_text": "Archive Archive"},
                {"url": current, "link_text": "What's On"},
            ],
            "events": [
                {"title": "Old exhibition", "listing_url": archive},
                {"title": "Current exhibition", "listing_url": current},
            ],
        },
    )

    payload = authority._state_payload(SimpleNamespace())

    assert [row["url"] for row in payload["listing_pages"]] == [current]
    assert [row["title"] for row in payload["events"]] == ["Current exhibition"]
    assert payload["retired_archive_listing_count"] == 1


def test_discovery_filter_removes_archive_candidate(monkeypatch) -> None:
    archive = SimpleNamespace(
        url="https://example.com/exhibition-archive.html",
        link_text="Archive",
    )
    current = SimpleNamespace(
        url="https://example.com/whats-on.html",
        link_text="What's On",
    )

    def discover(source, candidates, discovered_at, errors):
        candidates["archive"] = archive
        candidates["current"] = current

    monkeypatch.setattr(authority, "_BASE_DISCOVER_HOME_LINKS", discover)
    candidates = {}

    authority._discover_home_links({}, candidates, "now", [])

    assert candidates == {"current": current}


def test_manual_archive_url_is_rejected(tmp_path) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "artscience",
                        "name": "ArtScience Museum",
                        "allowed_domains": ["marinabaysands.com"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = EventReviewStore(tmp_path / "review", config)

    with pytest.raises(ValueError, match="archive or past-activities"):
        add_manual_listing(
            store,
            ManualListingRequest(
                source_id="artscience",
                url=(
                    "https://www.marinabaysands.com/museum/about-us/"
                    "exhibition-archive.html"
                ),
            ),
        )


def test_review_bootstrap_installs_archive_page_authority() -> None:
    source = (SURFACE / "local_events_runtime" / "review_summary_authority.py").read_text(
        encoding="utf-8"
    )

    assert "apply_listing_page_archive_authority" in source
    assert "apply_listing_page_archive_authority()" in source
