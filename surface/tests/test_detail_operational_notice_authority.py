from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_operational_notice_authority as authority  # noqa: E402
from local_events_runtime import review_detail_navigation_authority as navigation  # noqa: E402
from local_events_runtime import review_effective_fields_authority as effective  # noqa: E402

NOTICE = (
    "Notice: This activity space will be closed on 9, 16 and 20 May 2026, "
    "from 9:00am – 12:45pm, for a private programme. "
    "Thank you for your kind understanding."
)
ACTIVITY_DATE = "1 - 24 May 2026 (except Mondays)"
ACTIVITY_TIME = "9am - 10.45am | 11am - 12.45pm | 2pm - 3.45pm | 4pm - 5.45pm"
GARDENS_DATE = "Fri, 3 Jul - Mon, 10 Aug 2026"
GARDENS_TIME = "9.00am - 9.00pm"
GARDENS_PROMOTION = (
    "Visit Flower Dome from 3 Jul to 10 Aug 2026, scan the QR code and "
    "answer a simple question for a chance to win."
)
GARDENS_ADVISORY = "Advisory for use of tripods at Disney Garden of Wonder"


def _payload() -> dict:
    return {
        "dates": [NOTICE, ACTIVITY_DATE],
        "lines": [
            "[Free Drop-In Activity] Stamping the Coast",
            NOTICE,
            "Date",
            ACTIVITY_DATE,
            "Time",
            ACTIVITY_TIME,
            "Children's Museum Singapore",
        ],
    }


def test_closure_notice_is_not_selected_as_activity_date() -> None:
    assert authority._operational_notice(NOTICE)
    assert authority._detail_date_line(_payload()) == ACTIVITY_DATE


def test_notice_date_does_not_finish_detail_wait() -> None:
    assert not authority._facts_have_date({"dates": [NOTICE], "lines": [NOTICE]})
    assert authority._facts_have_date(_payload())


def test_when_uses_activity_date_and_hours_not_notice(monkeypatch) -> None:
    monkeypatch.setattr(effective, "_BASE_RAW_WHEN", lambda payload: NOTICE)

    when = authority._raw_when(_payload())

    assert when == f"{ACTIVITY_DATE} · {ACTIVITY_TIME}"
    assert "private programme" not in when
    assert "closed on" not in when


def test_gardens_preview_uses_opening_hours_not_promotion(monkeypatch) -> None:
    payload = {
        "dates": [GARDENS_DATE, GARDENS_PROMOTION],
        "times": [GARDENS_TIME],
        "venues": ["Flower Dome", GARDENS_ADVISORY],
        "lines": [
            "Orchid Extravaganza",
            "Date",
            GARDENS_DATE,
            GARDENS_PROMOTION,
            "Time",
            GARDENS_TIME,
            "Location",
            "Flower Dome",
            GARDENS_ADVISORY,
        ],
    }
    monkeypatch.setattr(
        effective,
        "_BASE_RAW_WHEN",
        lambda value: f"{GARDENS_PROMOTION} · {GARDENS_TIME}",
    )

    assert authority._detail_date_line(payload) == GARDENS_DATE
    assert authority._raw_when(payload) == f"{GARDENS_DATE} · {GARDENS_TIME}"
    assert navigation._raw_where(payload) == "Flower Dome"


def test_apply_rebinds_final_detail_date_owners(monkeypatch) -> None:
    monkeypatch.setattr(effective, "_detail_date_line", lambda payload: "wrong")
    monkeypatch.setattr(effective, "_facts_have_date", lambda payload: False)
    monkeypatch.setattr(effective, "_raw_when", lambda payload: "wrong")
    monkeypatch.setattr(navigation, "_raw_when", lambda payload: "wrong")

    authority.apply()

    assert effective._detail_date_line is authority._detail_date_line
    assert effective._facts_have_date is authority._facts_have_date
    assert effective._raw_when is authority._raw_when
    assert navigation._raw_when is authority._raw_when


def test_review_bootstrap_installs_operational_notice_authority() -> None:
    source = read_text("surface/local_events_runtime/review_summary_authority.py")

    assert "apply_detail_operational_notice_authority" in source
    assert "apply_detail_operational_notice_authority()" in source
