from __future__ import annotations

from pathlib import Path

import pytest

from surface.local_events_runtime import studio_pipeline

pytestmark = pytest.mark.backend


def test_pipeline_uses_active_runtime_root_and_committed_source_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("INFOSCREEN_ENV_DIR", str(runtime))
    observed: dict = {}

    def fake_apply(payload, *, root, source_config_path, browser_factory):
        observed.update(
            {
                "payload": payload,
                "root": root,
                "source_config_path": source_config_path,
                "browser_factory": browser_factory,
            }
        )
        return payload

    marker = object()
    monkeypatch.setattr(studio_pipeline, "apply_published_studio_rules", fake_apply)
    payload = {"results": [], "debug_by_source": []}
    assert studio_pipeline.apply_runtime_studio_rules(payload, browser_factory=lambda: marker) == {
        "results": [],
        "debug_by_source": [],
        "count": 0,
    }
    assert observed["root"] == runtime.resolve() / "local_event_studio"
    assert observed["source_config_path"] == studio_pipeline.SURFACE_DIR / "conf" / "event_sources.json"


def test_pipeline_synchronizes_detail_when_with_start_and_end_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        studio_pipeline,
        "apply_published_studio_rules",
        lambda payload, **kwargs: {
            "results": [
                {
                    "title": "Studio Event",
                    "when": "20 Jul 2099 - 22 Jul 2099",
                    "start_date": "2099-07-19",
                    "end_date": "2099-07-19",
                    "source_type": "studio_published_rule",
                },
                {
                    "title": "Legacy Event",
                    "when": "21 Jul 2099",
                    "start_date": "2099-07-01",
                    "source_type": "rendered_dom_card",
                },
            ],
            "debug_by_source": [],
        },
    )
    output = studio_pipeline.apply_runtime_studio_rules({})
    assert output["results"][0]["start_date"] == "2099-07-20"
    assert output["results"][0]["end_date"] == "2099-07-22"
    assert output["results"][1]["start_date"] == "2099-07-01"


def test_pipeline_marks_zero_acceptance_and_fatal_rules_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        studio_pipeline,
        "apply_published_studio_rules",
        lambda payload, **kwargs: {
            "results": [{"title": "Other source"}],
            "debug_by_source": [
                {
                    "source": "Esplanade",
                    "adapter": "studio_published_rule",
                    "accepted": 0,
                    "fatal_errors": [],
                    "status": "complete",
                    "complete": True,
                },
                {
                    "source": "National Gallery Singapore",
                    "adapter": "studio_published_rule",
                    "accepted": 1,
                    "fatal_errors": ["card_selector_invalid"],
                    "status": "complete",
                    "complete": True,
                },
                {
                    "source": "onePA / People's Association",
                    "adapter": "rendered_dom_card",
                    "accepted": 1,
                    "status": "complete",
                    "complete": True,
                },
            ],
        },
    )
    output = studio_pipeline.apply_runtime_studio_rules({})
    assert output["partial"] is True
    assert output["debug_by_source"][0]["complete"] is False
    assert output["debug_by_source"][0]["error"] == "studio_rule_no_accepted_events"
    assert output["debug_by_source"][1]["complete"] is False
    assert output["debug_by_source"][1]["error"] == "studio_rule_evaluation_failed"
    assert output["debug_by_source"][2]["complete"] is True
