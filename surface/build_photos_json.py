#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
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


def run(cmd):
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


def cache_url(path: Path, web_path: str) -> str:
    return f"{web_path}?v={int(path.stat().st_mtime)}"


def make_web_jpg(src: Path, dst: Path) -> bool:
    tmp = dst.with_suffix(".tmp.jpg")
    if tmp.exists():
        tmp.unlink()

    if shutil.which("magick"):
        ok = run(["magick", str(src), "-auto-orient", "-resize", "1800x1800>", "-quality", "88", "-strip", str(tmp)])
        if ok and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True

    shutil.copy2(src, dst)
    return dst.exists() and dst.stat().st_size > 0


def convert_heic(src: Path, dst: Path) -> bool:
    tmp = dst.with_suffix(".tmp.jpg")
    if tmp.exists():
        tmp.unlink()

    if shutil.which("ffmpeg"):
        ok = run(["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", "-update", "1", str(tmp)])
        if ok and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True
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


def output_name(path: Path, suffix: str) -> str:
    return f"{path.stem}{suffix}"


def main() -> None:
    ENV_DIR.mkdir(exist_ok=True)
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    sources = photo_sources()
    native_stems = {path.stem for path in sources if path.suffix.lower() in (NATIVE_EXTS | GIF_EXTS)}

    for path in sources:
        ext = path.suffix.lower()

        if ext in NATIVE_EXTS:
            out = OUT_DIR / output_name(path, ".jpg")
            if not out.exists() or path.stat().st_mtime > out.stat().st_mtime:
                if not make_web_jpg(path, out):
                    print(f"SKIP: cannot normalize {path}")
                    continue
            items.append({"src": cache_url(out, "public_photos/" + out.name), "name": path.stem, "type": "native-normalized", "source_path": str(path)})

        elif ext in GIF_EXTS:
            out = OUT_DIR / path.name
            if not out.exists() or path.stat().st_mtime > out.stat().st_mtime:
                shutil.copy2(path, out)
            items.append({"src": cache_url(out, "public_photos/" + out.name), "name": path.stem, "type": "gif-copy", "source_path": str(path)})

        elif ext in HEIC_EXTS:
            if path.stem in native_stems:
                print(f"SKIP HEIC because native image exists: {path.name}")
                continue
            out = OUT_DIR / output_name(path, ".jpg")
            if not out.exists() or path.stat().st_mtime > out.stat().st_mtime:
                if not convert_heic(path, out):
                    print(f"SKIP: cannot convert {path}")
                    continue
            items.append({"src": cache_url(out, "public_photos/" + out.name), "name": path.stem, "type": "heic-converted", "source_path": str(path)})

    OUT_JSON.write_text(json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds"), "source_dir": str(SRC_DIR), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}, photos={len(items)}")


if __name__ == "__main__":
    main()
