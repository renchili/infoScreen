from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "surface"
WEB = SURFACE / "web"
FIXTURES = ROOT / "tests" / "fixtures"
RUNTIME_FIXTURES = FIXTURES / "runtime_data"


def read_text(path: str | Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def read_json(path: str | Path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.fixture()
def seeded_env(tmp_path: Path) -> Path:
    target = tmp_path / ".env"
    target.mkdir()
    for source in RUNTIME_FIXTURES.glob("*.json"):
        shutil.copy2(source, target / source.name)
    public_photos = target / "public_photos"
    public_photos.mkdir()
    (public_photos / "fixture-photo.txt").write_text("fixture photo bytes\n", encoding="utf-8")
    return target
