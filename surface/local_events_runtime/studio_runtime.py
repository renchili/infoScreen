from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .studio_collect import apply_published_studio_rules

SURFACE_DIR = Path(__file__).resolve().parents[1]


def runtime_env_dir() -> Path:
    """Resolve the same machine-local runtime root used by the HTTP server and jobs."""

    return Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(SURFACE_DIR / ".env"))
    ).expanduser().resolve()


def apply_runtime_studio_rules(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply active Studio rules without changing payloads when none are published."""

    return apply_published_studio_rules(
        payload,
        root=runtime_env_dir() / "local_event_studio",
        source_config_path=SURFACE_DIR / "conf" / "event_sources.json",
    )


__all__ = ["apply_runtime_studio_rules", "runtime_env_dir"]
