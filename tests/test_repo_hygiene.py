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

LOCAL_ARTIFACT_PREFIXES = (
    "logs/",
    "photos/",
    "public_photos/",
)

SCAN_EXCLUDED_PREFIXES = (
    "tests/",
    ".git/",
)

SCAN_EXCLUDED_FILES = {
    "docs/engineering-quality.md",
}


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
        if raw in SCAN_EXCLUDED_FILES:
            continue

        if raw.startswith(SCAN_EXCLUDED_PREFIXES):
            continue

        path = Path(raw)

        if not path.is_file():
            continue

        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        out.append(path)

    return out


def private_path_patterns() -> list[re.Pattern[str]]:
    user_name = "rody"

    unix_home = "/".join(("", "home", user_name))
    mac_home = "/".join(("", "Users", user_name))
    win_home = "C:" + "\\" + "Users" + "\\"

    return [
        re.compile(re.escape(unix_home) + r"\b"),
        re.compile(re.escape(mac_home) + r"\b"),
        re.compile(re.escape(win_home), re.IGNORECASE),
    ]


PRIVATE_IP_PATTERN = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"
)

SECRET_WORD_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}",
    re.IGNORECASE,
)


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
        or path.startswith(LOCAL_ARTIFACT_PREFIXES)
    ]

    assert not bad, f"local artifacts must not be tracked: {bad}"


def test_no_private_paths_or_obvious_secrets_in_project_files() -> None:
    offenders: list[str] = []
    patterns = private_path_patterns()

    for path in text_files(git_ls_files()):
        text = path.read_text(encoding="utf-8")

        if any(pattern.search(text) for pattern in patterns):
            offenders.append(f"{path}: private home path")

        if PRIVATE_IP_PATTERN.search(text):
            offenders.append(f"{path}: private IPv4 address")

        if SECRET_WORD_PATTERN.search(text):
            offenders.append(f"{path}: possible secret")

    assert not offenders, "\n".join(offenders)
