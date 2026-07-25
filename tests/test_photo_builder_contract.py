from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from surface import build_photos_json
from .conftest import read_text

pytestmark = pytest.mark.backend


def test_png_is_not_renamed_to_jpg_without_a_real_converter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sample.png"
    target = tmp_path / "sample-png.jpg"
    source.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-jpeg")
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    assert build_photos_json.make_web_jpg(source, target) is False
    assert not target.exists()


def test_native_output_names_do_not_collide_across_formats() -> None:
    assert build_photos_json.normalized_output_name(Path("photo.jpg")) == "photo.jpg"
    assert build_photos_json.normalized_output_name(Path("photo.jpeg")) == "photo.jpg"
    assert build_photos_json.normalized_output_name(Path("photo.png")) == "photo-png.jpg"
    assert build_photos_json.normalized_output_name(Path("photo.webp")) == "photo-webp.jpg"


def test_public_photo_manifest_does_not_include_private_source_paths() -> None:
    source = read_text("surface/build_photos_json.py")

    assert '"source_path"' not in source
    assert '"source_dir"' not in source
    assert '"items": items' in source
    assert "atomic_write_json(OUT_JSON, payload)" in source
