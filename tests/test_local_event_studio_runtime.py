from __future__ import annotations

from pathlib import Path

import pytest

from surface.local_events_runtime import studio_pipeline, studio_runtime

pytestmark = pytest.mark.backend


def test_runtime_env_dir_uses_active_infoscreen_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFOSCREEN_ENV_DIR", str(tmp_path / "runtime"))
    assert studio_runtime.runtime_env_dir() == (tmp_path / "runtime").resolve()


def test_runtime_module_reexports_the_single_pipeline_implementation() -> None:
    assert studio_runtime.apply_runtime_studio_rules is studio_pipeline.apply_runtime_studio_rules
    assert studio_runtime.runtime_env_dir is studio_pipeline.runtime_env_dir
