#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

SURFACE_DIR = Path(__file__).resolve().parent
ENV_DIR = SURFACE_DIR / ".env"
SRC_DIR = ENV_DIR / "photos"
OUT_DIR = ENV_DIR / "public_photos"
OUT_JSON = ENV_DIR / "photos.json"

SRC_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

NATIVE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
GIF_EXTS = {".gif"}
HEIC_EXTS = {".heic", ".heif"}


def run(cmd: list[str]) -> bool:
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        print("FAILED:", " ".join(cmd))
        if result.stdout.strip():
            print("STDOUT:", result.stdout.strip())
        if result.stderr.strip():
            print("STDERR:", result.stderr.strip())
        return False
    return True


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def cache_url(path: Path, web_path: str) -> str:
    return f"{web_path}?v={int(path.stat().st_mtime)}"


def normalized_output_name(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return f"{path.stem}.jpg"
    return f"{path.stem}-{ext.removeprefix('.').lower()}.jpg"


def make_web_jpg(src: Path, dst: Path) -> bool:
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp.jpg")
    if tmp.exists():
        tmp.unlink()

    if shutil.which("magick"):
        ok = run(
            [
                "magick",
                str(src),
                "-auto-orient",
                "-resize",
                "1800x1800>",
                "-quality",
                "88",
                "-strip",
                str(tmp),
            ]
        )
        if ok and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True

    if src.suffix.lower() in {".jpg", ".jpeg"}:
        shutil.copy2(src, tmp)
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True

    if tmp.exists():
        tmp.unlink()
    return False


def convert_heic(src: Path, dst: Path) -> bool:
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp.jpg")
    if tmp.exists():
        tmp.unlink()

    if shutil.which("ffmpeg"):
        ok = run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(tmp),
            ]
        )
        if ok and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True
    if tmp.exists():
        tmp.unlink()
    return False


def photo_sources() -> list[Path]:
    out = []
    for path in sorted(SRC_DIR.iterdir()):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in (NATIVE_EXTS | GIF_EXTS | HEIC_EXTS):
            continue
        out.append(path)
    return out


def main() -> None:
    ENV_DIR.mkdir(exist_ok=True)
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    sources = photo_sources()
    native_stems = {
        path.stem
        for path in sources
        if path.suffix.lower() in (NATIVE_EXTS | GIF_EXTS)
    }

    for path in sources:
        ext = path.suffix.lower()

        if ext in NATIVE_EXTS:
            out = OUT_DIR / normalized_output_name(path)
            if not out.exists() or path.stat().st_mtime > out.stat().st_mtime:
                if not make_web_jpg(path, out):
                    print(
                        f"SKIP: cannot normalize {path.name}; "
                        "install ImageMagick for PNG/WebP conversion"
                    )
                    continue
            items.append(
                {
                    "src": cache_url(out, "/public_photos/" + out.name),
                    "name": path.stem,
                    "type": "native-normalized",
                }
            )

        elif ext in GIF_EXTS:
            out = OUT_DIR / path.name
            if not out.exists() or path.stat().st_mtime > out.stat().st_mtime:
                temporary = OUT_DIR / f".{path.name}.{os.getpid()}.tmp"
                shutil.copy2(path, temporary)
                temporary.replace(out)
            items.append(
                {
                    "src": cache_url(out, "/public_photos/" + out.name),
                    "name": path.stem,
                    "type": "gif-copy",
                }
            )

        elif ext in HEIC_EXTS:
            if path.stem in native_stems:
                print(f"SKIP HEIC because native image exists: {path.name}")
                continue
            out = OUT_DIR / f"{path.stem}-heic.jpg"
            if not out.exists() or path.stat().st_mtime > out.stat().st_mtime:
                if not convert_heic(path, out):
                    print(f"SKIP: cannot convert {path.name}; install ffmpeg")
                    continue
            items.append(
                {
                    "src": cache_url(out, "/public_photos/" + out.name),
                    "name": path.stem,
                    "type": "heic-converted",
                }
            )

    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }
    atomic_write_json(OUT_JSON, payload)
    print(f"wrote {OUT_JSON}, photos={len(items)}")


if __name__ == "__main__":
    main()
