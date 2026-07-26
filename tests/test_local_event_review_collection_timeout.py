from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_review as review  # noqa: E402
from local_events_runtime import review_collection_timeout_authority as authority  # noqa: E402


def _store(tmp_path: Path) -> review.EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    return review.EventReviewStore(
        root=tmp_path / "review",
        config_path=config,
    )


def test_timeout_kills_worker_group_and_preserves_previous_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    previous = review.ReviewState(event_collection={"marker": "previous"})
    store.save(previous)

    class FakeProcess:
        pid = 43210
        returncode = None

        def communicate(self, timeout: int):
            raise subprocess.TimeoutExpired("collector", timeout)

        def poll(self):
            return None

    process = FakeProcess()
    terminated: list[object] = []
    monkeypatch.setattr(authority.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        authority,
        "_terminate_process_group",
        lambda value: terminated.append(value),
    )
    monkeypatch.setattr(authority, "timeout_seconds", lambda: 31)

    with pytest.raises(
        authority.ReviewCollectionTimeout,
        match="review_event_collection_timeout_after_31_seconds",
    ):
        authority.collect_event_candidates(store)

    assert terminated == [process]
    assert store.load().event_collection == {"marker": "previous"}
    assert list(store.root.glob(".collection-result.*.json")) == []


def test_success_returns_worker_result_and_removes_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    expected = review.ReviewState(
        event_collection={
            "completed_at": "2026-07-26T00:00:00+00:00",
            "candidate_count": 0,
        }
    )

    def fake_run(
        current_store: review.EventReviewStore,
        result_path: Path,
        timeout: int,
    ) -> None:
        assert current_store is store
        assert timeout == 45
        result_path.write_text(expected.model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(authority, "_run_isolated_collection", fake_run)
    monkeypatch.setattr(authority, "timeout_seconds", lambda: 45)

    result = authority.collect_event_candidates(store)

    assert result.event_collection == expected.event_collection
    assert list(store.root.glob(".collection-result.*.json")) == []


def test_worker_command_marks_child_and_uses_surface_module_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result_path = store.root / "result.json"

    command, environment, cwd = authority._worker_command(store, result_path)

    assert command[:3] == [
        sys.executable,
        "-m",
        "local_events_runtime.review_collection_timeout_authority",
    ]
    assert environment[authority._CHILD_ENV] == "1"
    assert cwd == SURFACE
    assert str(store.root) in command
    assert str(store.config_path) in command
    assert str(result_path) in command


def test_child_apply_does_not_wrap_collector_recursively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    monkeypatch.setenv(authority._CHILD_ENV, "1")
    monkeypatch.setattr(authority, "_APPLIED", False)
    monkeypatch.setattr(review, "collect_event_candidates", sentinel)

    authority.apply()

    assert review.collect_event_candidates is sentinel


def test_timeout_authority_is_installed_after_diagnostic_collector() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")
    summary = read_text("surface/local_events_runtime/review_summary_authority.py")

    assert bootstrap.index("apply_event_review_diagnostics()") < bootstrap.index(
        "apply_review_summary_authority()"
    )
    assert "apply_review_collection_timeout_authority()" in summary
