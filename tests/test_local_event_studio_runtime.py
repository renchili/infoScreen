from __future__ import annotations

from pathlib import Path

import pytest

from surface.local_events_runtime import studio_runtime

pytestmark = pytest.mark.backend


def test_runtime_env_dir_uses_active_infoscreen_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFOSCREEN_ENV_DIR", str(tmp_path / "runtime"))
    assert studio_runtime.runtime_env_dir() == (tmp_path / "runtime").resolve()


def test_runtime_bridge_passes_local_studio_and_committed_source_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("INFOSCREEN_ENV_DIR", str(runtime))
    observed: dict = {}

    def fake_apply(payload, *, root, source_config_path):
        observed["payload"] = payload
        observed["root"] = root
        observed["source_config_path"] = source_config_path
        return {**payload, "bridge": "called"}

    monkeypatch.setattr(studio_runtime, "apply_published_studio_rules", fake_apply)
    payload = {"results": [{"title": "legacy"}]}
    output = studio_runtime.apply_runtime_studio_rules(payload)

    assert output["bridge"] == "called"
    assert observed["payload"] is payload
    assert observed["root"] == runtime.resolve() / "local_event_studio"
    assert observed["source_config_path"] == studio_runtime.SURFACE_DIR / "conf" / "event_sources.json"
