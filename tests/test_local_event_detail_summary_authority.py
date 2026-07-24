from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_summary_authority as authority  # noqa: E402


authority.apply()


ACTIVITY_INTRO = (
    "Race across Pulau Ubin with animal friends and discover how wildlife adapted "
    "to the island through an interactive installation and craft activity."
)
TERMS_TEXT = (
    "This programme is based on a first-come-first-served basis. "
    "For further enquiries, please email cmsg_prg@heritage.sg. "
    "Terms & Conditions: This programme is free, but donations are encouraged. "
    "No pre-registration is required. For safety, children must be accompanied."
)


def test_childrens_museum_terms_are_not_an_activity_summary() -> None:
    assert authority.useful_event_summary(TERMS_TEXT) == ""


def test_activity_intro_is_preserved_before_terms_and_contact_details() -> None:
    combined = f"{ACTIVITY_INTRO} Terms & Conditions: {TERMS_TEXT}"

    assert authority.useful_event_summary(combined) == ACTIVITY_INTRO


def test_contact_and_first_come_text_cannot_win_by_being_longer() -> None:
    long_operational = (
        "This programme is based on a first-come-first-served basis. "
        + "For further enquiries, please email cmsg_prg@heritage.sg. " * 8
    )

    assert authority.useful_event_summary(long_operational) == ""
    assert authority.useful_event_summary(ACTIVITY_INTRO) == ACTIVITY_INTRO


def test_browser_summary_selection_stops_at_operational_sections() -> None:
    script = authority.SECTIONED_DETAIL_JS.lower()

    assert "terms?\\s*(?:&|and)\\s*conditions" in script
    assert "first[-\\s]?come[-\\s]?first[-\\s]?served" in script
    assert "for\\s+(?:further\\s+)?enquir" in script
    assert "pre[-\\s]?registration" in script
    assert "for\\s+safety" in script
    assert "operationalsection" in script
    assert "narrativelines" in script
    assert "right.score - left.score || left.position - right.position" in script


def test_summary_authority_is_applied_before_final_review_binding() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    detail_payload = bootstrap.index("apply_detail_payload_authority()")
    detail_summary = bootstrap.index("apply_detail_summary_authority()")
    binding = bootstrap.index("_bind_final_browser_runtime_to_review()")

    assert detail_payload < detail_summary < binding


def test_canonical_job_reaches_section_aware_summary_through_review_authority() -> None:
    review_authority = read_text(
        "surface/local_events_runtime/review_summary_authority.py"
    )
    job = read_text("surface/jobs/local_event_search.py")

    assert "apply_detail_summary_authority()" in review_authority
    assert "review_summary_authority.apply()" in job
