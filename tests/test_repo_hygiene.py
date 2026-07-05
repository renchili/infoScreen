from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import ROOT

pytestmark = pytest.mark.scripts


def test_no_root_level_browser_assets() -> None:
    assert sorted(path.name for path in ROOT.glob("*.css")) == []
    assert sorted(path.name for path in ROOT.glob("*.js")) == []


def test_no_legacy_surface_web_browser_assets() -> None:
    web = ROOT / "surface" / "web"
    assert sorted(path.name for path in web.glob("*.css")) == []
    assert sorted(path.name for path in web.glob("*.js")) == []


def test_no_committed_runtime_or_generated_artifact_dirs() -> None:
    forbidden: list[Path] = [
        ROOT / ".env",
        ROOT / "surface" / ".env",
        ROOT / "logs",
        ROOT / "test-results",
        ROOT / "artifacts",
        ROOT / "photo",
        ROOT / "photos",
        ROOT / "public_photos",
    ]
    assert [path for path in forbidden if path.exists()] == []


def test_allowed_root_inventory() -> None:
    allowed_files = {"README.md", "AGENTS.md", "AGENT.md", "metadata.json", "pyproject.toml", ".gitignore"}
    allowed_dirs = {".git", ".githooks", ".github", "docs", "skills", "surface", "deploy", "mac", "scripts", "tests"}
    bad = []
    for path in ROOT.iterdir():
        name = path.name
        if path.is_file() and name not in allowed_files:
            bad.append(name)
        if path.is_dir() and name not in allowed_dirs:
            bad.append(name + "/")
    assert sorted(bad) == []
