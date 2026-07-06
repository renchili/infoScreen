#!/usr/bin/env python3
"""Independent repository quality suites for local, PR, and post-merge checks."""

import argparse
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

TEXT_SUFFIXES = {
    ".css", ".html", ".js", ".json", ".md", ".py",
    ".sh", ".txt", ".yml", ".yaml", ".plist", ".conf",
}

ROOT_ALLOW_FILES = {
    ".gitignore", "AGENT.md", "AGENTS.md", "README.md", "metadata.json", "pyproject.toml",
}

ROOT_ALLOW_DIRS = {
    ".github", ".githooks", "deploy", "docs", "mac", "scripts", "skills", "surface", "tests",
}

RUNTIME_BASENAMES = {
    "event_stream.json", "local_event_search_results.json", "market.json", "market_config.json",
    "metrics.json", "photos.json", "schedule.json", "sync_status.json", "weather.json",
}

RUNTIME_PREFIXES = (
    ".env/", "surface/.env/", "logs/", "photo/", "photos/", "public_photos/",
    "test-results/", "artifacts/", "htmlcov/",
)

RUNTIME_PARTS = {"__pycache__", ".pytest_cache"}

OBSOLETE_LOCAL_EVENT_NAMES = (
    "local_events_controls", "local_events_compact", "local_events_carousel", "local_events_panel_v3",
)

FORBIDDEN_UI_TEXT = ("official calendars",)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PRIVATE_IPV4_RE = re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})\b")
ABSOLUTE_HOME_RE = re.compile(r"(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)")
SECRET_RE = re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9]{16,})\b")
CONFLICT_RE = re.compile(r"^(?:<{7}[^\n]*|={7}|>{7}[^\n]*)$", re.MULTILINE)

SUITES = ("paths", "content", "structure", "python", "all")
SCOPES = ("changed", "repository")


def git_output(args):
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError("git command failed: git " + " ".join(args) + "\n" + result.stderr)
    return result.stdout


def split_null_output(text):
    return [item for item in text.split("\0") if item]


def changed_paths(base, head, include_working_tree):
    names = set(split_null_output(git_output(["diff", "--name-only", "-z", f"{base}...{head}"])))
    if include_working_tree:
        names.update(split_null_output(git_output(["diff", "--name-only", "-z"])))
        names.update(split_null_output(git_output(["diff", "--cached", "--name-only", "-z"])))
        names.update(split_null_output(git_output(["ls-files", "--others", "--exclude-standard", "-z"])))
    return sorted(names)


def repository_paths(include_working_tree):
    names = set(split_null_output(git_output(["ls-files", "-z"])))
    if include_working_tree:
        names.update(split_null_output(git_output(["ls-files", "--others", "--exclude-standard", "-z"])))
    return sorted(names)


def selected_paths(args):
    if args.scope == "repository":
        return repository_paths(args.include_working_tree)
    if not args.base:
        raise ValueError("--base is required when --scope changed is selected")
    return changed_paths(args.base, args.head, args.include_working_tree)


def is_text_file(path):
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"README", "README.md", ".gitignore"}


def add_error(errors, relative, message):
    errors.append(f"{relative}: {message}")


def under_test_fixture(normalized):
    return normalized.startswith("tests/fixtures/")


def check_path_policy(relative, errors):
    normalized = relative.replace("\\", "/")
    path = Path(normalized)
    parts = normalized.split("/")
    name = path.name.lower()
    suffix = path.suffix.lower()

    if len(parts) == 1:
        if path.name not in ROOT_ALLOW_FILES:
            add_error(errors, relative, "root file is outside the repository root allowlist")
        if suffix in {".css", ".js"}:
            add_error(errors, relative, "root browser asset is not an active source path")
    elif parts[0] not in ROOT_ALLOW_DIRS:
        add_error(errors, relative, "top-level directory is outside the repository root allowlist")

    if len(parts) == 3 and parts[0] == "surface" and parts[1] == "web" and suffix in {".css", ".js"}:
        add_error(errors, relative, "legacy direct surface/web browser asset; use surface/web/assets")

    if any(normalized.startswith(prefix) for prefix in RUNTIME_PREFIXES):
        add_error(errors, relative, "runtime/generated/local artifact path must not be committed")

    if any(part in RUNTIME_PARTS for part in parts):
        add_error(errors, relative, "cache path must not be committed")

    if name in RUNTIME_BASENAMES and not under_test_fixture(normalized):
        add_error(errors, relative, "runtime/generated JSON must not be committed outside fixtures")

    if suffix in {".pyc", ".tmp", ".log", ".bak", ".backup"} or ".bak" in name or name.endswith(".back"):
        add_error(errors, relative, "generated, cache, log, or backup file must not be committed")

    if any(token in name for token in OBSOLETE_LOCAL_EVENT_NAMES):
        add_error(errors, relative, "obsolete Local Event overlay file is blocked")


def check_text_content(relative, text, errors):
    if CONFLICT_RE.search(text):
        add_error(errors, relative, "unresolved merge-conflict marker found")

    for match in EMAIL_RE.finditer(text):
        email = match.group(0).lower()
        if email.endswith("@example.com"):
            continue
        add_error(errors, relative, "email address detected")
        break

    if PRIVATE_IPV4_RE.search(text):
        add_error(errors, relative, "private IPv4 address detected")

    if ABSOLUTE_HOME_RE.search(text):
        add_error(errors, relative, "absolute personal home path detected")

    if SECRET_RE.search(text):
        add_error(errors, relative, "possible access token or secret detected")

    if relative == "surface/web/index.html":
        lowered = text.lower()
        for token in FORBIDDEN_UI_TEXT:
            if token in lowered:
                add_error(errors, relative, f'blocked UI content detected: "{token}"')
        for token in OBSOLETE_LOCAL_EVENT_NAMES:
            if token in lowered:
                add_error(errors, relative, f"obsolete Local Event layer reference detected: {token}")


def check_html_structure(relative, text, errors):
    lowered = text.lower()
    if lowered.count("<html") != 1:
        add_error(errors, relative, "expected exactly one <html> element")
    if lowered.count("</html>") != 1:
        add_error(errors, relative, "expected exactly one </html> element")
    if "</head>" not in lowered or "</body>" not in lowered:
        add_error(errors, relative, "missing </head> or </body>")


def check_json(relative, path, errors):
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_error(errors, relative, f"invalid JSON: {exc}")


def check_python_syntax(errors):
    raw = git_output(["ls-files", "-z", "--", "*.py"])
    for relative in split_null_output(raw):
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            add_error(errors, relative, f"Python syntax error: {exc.msg}")


def run_paths_suite(paths, errors):
    for relative in paths:
        check_path_policy(relative, errors)


def run_content_suite(paths, errors):
    for relative in paths:
        path = ROOT / relative
        if path.is_file() and is_text_file(path):
            check_text_content(relative, path.read_text(encoding="utf-8", errors="replace"), errors)


def run_structure_suite(paths, errors):
    for relative in paths:
        path = ROOT / relative
        if not path.is_file():
            continue
        if path.suffix.lower() == ".json":
            check_json(relative, path, errors)
        if relative == "surface/web/index.html":
            check_html_structure(relative, path.read_text(encoding="utf-8", errors="replace"), errors)


def run_suite(name, paths, errors):
    if name in ("paths", "all"):
        run_paths_suite(paths, errors)
    if name in ("content", "all"):
        run_content_suite(paths, errors)
    if name in ("structure", "all"):
        run_structure_suite(paths, errors)
    if name in ("python", "all"):
        check_python_syntax(errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=SUITES, default="all")
    parser.add_argument("--scope", choices=SCOPES, default="changed")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--include-working-tree", action="store_true")
    args = parser.parse_args()

    try:
        paths = selected_paths(args)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    errors = []
    run_suite(args.suite, paths, errors)

    if errors:
        print(f"FAILED suite={args.suite} scope={args.scope}")
        for error in errors:
            print(f" - {error}")
        return 1

    print(f"PASSED suite={args.suite} scope={args.scope} files={len(paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
