#!/usr/bin/env python3
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "infoscreen"
SRC_DIR = BASE / "photos"
OUT_DIR = BASE / "public_photos"
OUT_JSON = BASE / "photos.json"

SRC_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

NATIVE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
GIF_EXTS = {".gif"}
HEIC_EXTS = {".heic", ".heif"}

def run(cmd):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        if r.stdout.strip():
            print("STDOUT:", r.stdout.strip())
        if r.stderr.strip():
            print("STDERR:", r.stderr.strip())
        return False
    return True

def cache_url(path: Path, web_path: str) -> str:
    return f"{web_path}?v={int(path.stat().st_mtime)}"

def make_web_jpg(src: Path, dst: Path) -> bool:
    tmp = dst.with_suffix(".tmp.jpg")
    if tmp.exists():
        tmp.unlink()

    # 关键：-auto-orient 把 iPhone EXIF 方向真正写进像素里
    if shutil.which("magick"):
        ok = run([
            "magick",
            str(src),
            "-auto-orient",
            "-resize", "1800x1800>",
            "-quality", "88",
            "-strip",
            str(tmp),
        ])
        if ok and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True

    # 没有 magick 就直接复制，但方向可能不对
    shutil.copy2(src, dst)
    return dst.exists() and dst.stat().st_size > 0

def convert_heic(src: Path, dst: Path) -> bool:
    tmp = dst.with_suffix(".tmp.jpg")
    if tmp.exists():
        tmp.unlink()

    # HEIC 仅兜底；如果有同名 JPG，会跳过 HEIC
    if shutil.which("ffmpeg"):
        ok = run([
            "ffmpeg", "-y",
            "-i", str(src),
            "-frames:v", "1",
            "-update", "1",
            str(tmp),
        ])
        if ok and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dst)
            return True

    return False

items = []

# 如果同名 JPG/PNG 存在，HEIC 不处理
native_stems = {
    p.stem for p in SRC_DIR.iterdir()
    if p.is_file() and p.suffix.lower() in (NATIVE_EXTS | GIF_EXTS)
}

for p in sorted(SRC_DIR.iterdir()):
    if not p.is_file():
        continue

    ext = p.suffix.lower()

    if ext in NATIVE_EXTS:
        out = OUT_DIR / f"{p.stem}.jpg"

        if not out.exists() or p.stat().st_mtime > out.stat().st_mtime:
            ok = make_web_jpg(p, out)
            if not ok:
                print(f"SKIP: cannot normalize {p}")
                continue

        items.append({
            "src": cache_url(out, "public_photos/" + out.name),
            "name": p.stem,
            "type": "native-normalized",
        })

    elif ext in GIF_EXTS:
        out = OUT_DIR / p.name
        if not out.exists() or p.stat().st_mtime > out.stat().st_mtime:
            shutil.copy2(p, out)

        items.append({
            "src": cache_url(out, "public_photos/" + out.name),
            "name": p.stem,
            "type": "gif-copy",
        })

    elif ext in HEIC_EXTS:
        if p.stem in native_stems:
            print(f"SKIP HEIC because native image exists: {p.name}")
            continue

        out = OUT_DIR / f"{p.stem}.jpg"
        if not out.exists() or p.stat().st_mtime > out.stat().st_mtime:
            ok = convert_heic(p, out)
            if not ok:
                print(f"SKIP: cannot convert {p}")
                continue

        items.append({
            "src": cache_url(out, "public_photos/" + out.name),
            "name": p.stem,
            "type": "heic-converted",
        })

OUT_JSON.write_text(json.dumps({
    "updated_at": datetime.now().isoformat(timespec="seconds"),
    "items": items,
}, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"wrote {OUT_JSON}, photos={len(items)}")
