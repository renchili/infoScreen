#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = Path(os.environ.get("ACCEPTANCE_ARTIFACT_DIR", "/tmp/infoscreen-acceptance"))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def names(paths: list[Path]) -> list[str]:
    return sorted(rel(path) for path in paths)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    inventory = {
        "root_css": names(list(ROOT.glob("*.css"))),
        "root_js": names(list(ROOT.glob("*.js"))),
        "legacy_surface_web_css": names(list((ROOT / "surface" / "web").glob("*.css"))),
        "legacy_surface_web_js": names(list((ROOT / "surface" / "web").glob("*.js"))),
        "root_inventory": sorted(path.name + ("/" if path.is_dir() else "") for path in ROOT.iterdir()),
        "runtime_or_generated_paths": names([
            path for path in ROOT.rglob("*")
            if path.is_file()
            and (
                "/.env/" in "/" + rel(path)
                or "/__pycache__/" in "/" + rel(path)
                or "/.pytest_cache/" in "/" + rel(path)
                or rel(path).startswith(("logs/", "photo/", "photos/", "public_photos/", "test-results/", "artifacts/"))
                or path.suffix in {".pyc", ".tmp", ".log", ".bak", ".backup"}
            )
        ]),
    }
    out = ARTIFACT_DIR / "static-inventory.json"
    out.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(inventory, ensure_ascii=False, indent=2))
    for key in ["root_css", "root_js", "legacy_surface_web_css", "legacy_surface_web_js", "runtime_or_generated_paths"]:
        if inventory[key]:
            raise SystemExit(f"static inventory violation: {key}")


if __name__ == "__main__":
    main()
