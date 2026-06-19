from __future__ import annotations

import re
import subprocess
from pathlib import Path


RUNTIME_FILES = {
    "schedule.json",
    "weather.json",
    "market.json",
    "event_stream.json",
    "local_event_search_results.json",
    "photos.json",
    "index2.html",
}

FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"/home/rody\b"),
    re.compile(r"/Users/rody\b"),
    re.compile(r"C:\\Users\\", re.IGNORECASE),
]

PRIVATE_IP_PATTERN = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"
)

SECRET_WORD_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}",
    re.IGNORECASE,
)


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.splitlines()


def text_files(paths: list[str]) -> list[Path]:
    out: list[Path] = []

    for raw in paths:
        path = Path(raw)

        if not path.is_file():
            continue

        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        out.append(path)

    return out


def test_runtime_files_are_not_tracked() -> None:
    tracked = set(git_ls_files())
    bad = sorted(RUNTIME_FILES & tracked)
    assert not bad, f"runtime files must not be tracked: {bad}"


def test_no_backup_or_local_artifacts_are_tracked() -> None:
    bad = [
        path
        for path in git_ls_files()
        if path.endswith(".bak")
        or ".bak." in path
        or path.startswith("logs/")
        or path.startswith("photos/")
        or path.startswith("public_photos/")
    ]

    assert not bad, f"local artifacts must not be tracked: {bad}"


def test_no_private_paths_or_obvious_secrets() -> None:
    offenders: list[str] = []

    for path in text_files(git_ls_files()):
        text = path.read_text(encoding="utf-8")

        if any(pattern.search(text) for pattern in FORBIDDEN_PATH_PATTERNS):
            offenders.append(f"{path}: private home path")

        if PRIVATE_IP_PATTERN.search(text):
            offenders.append(f"{path}: private IPv4 address")

        if SECRET_WORD_PATTERN.search(text):
            offenders.append(f"{path}: possible secret")

    assert not offenders, "\n".join(offenders)
