from __future__ import annotations

from pathlib import Path


HTML = Path("index.html")


def html() -> str:
    return HTML.read_text(encoding="utf-8")


def test_index_has_main_dashboard_regions() -> None:
    text = html()

    required = [
        "marketList",
        "localEventBox",
        "localPlaceForm",
        "localPlaceInput",
        "localNoticeList",
        "event stream",
        "photoFlipWall",
        "weatherTemp",
        "weatherDesc",
        "calendar",
        "POWER",
        "DISPLAY",
        "NETWORK",
        "UPTIME",
    ]

    missing = [item for item in required if item not in text]
    assert not missing, f"index.html missing UI regions: {missing}"


def test_local_event_is_not_single_static_item() -> None:
    text = html()

    required = [
        "local-event-inline-script",
        "local_event_search_results.json",
        "localOffset",
        "rotate",
    ]

    missing = [item for item in required if item not in text]
    assert not missing, f"local-event carousel contract missing: {missing}"

    forbidden = [
        "official calendars",
        "OFFICIAL CALENDARS",
    ]

    present = [item for item in forbidden if item in text]
    assert not present, f"forbidden local-event text present: {present}"
