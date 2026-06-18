#!/usr/bin/env python3
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

RUNTIME_BASENAMES = {
    "schedule.json",
    "weather.json",
    "market.json",
    "metrics.json",
    "event_stream.json",
    "local_event_search_results.json",
    "photos.json",
}

RUNTIME_PREFIXES = (
    "logs/",
    "photos/",
    "public_photos/",
)

OBSOLETE_LOCAL_EVENT_NAMES = (
    "local_events_controls",
    "local_events_compact",
    "local_events_carousel",
    "local_events_panel_v3",
)

FORBIDDEN_UI_TEXT = (
    "official calendars",
)

EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PRIVATE_IPV4_RE = re.compile(
    r"\b(?:"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}"
    r")\b"
)

ABSOLUTE_HOME_RE = re.compile(
    r"(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|"
    r"[A-Za-z]:\\Users\\[^\\\s]+\\)"
)

SECRET_RE = re.compile(
    r"\b(?:"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|"
    r"AKIA[A-Z0-9]{16}|"
    r"sk-[A-Za-z0-9]{16,}"
    r")\b"
)

# Match only actual Git conflict-marker lines. Do not flag source code that
# contains the marker text inside a quoted string.
CONFLICT_RE = re.compile(
    r"^(?:<{7}[^\n]*|={7}|>{7}[^\n]*)$",
    re.MULTILINE,
)


def git_output(args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "git command failed: git " + " ".join(args) + "\n" + result.stderr
        )
    return result.stdout


def changed_paths(base, head, include_working_tree):
    names = set()

    def add_lines(text):
        for line in text.splitlines():
            line = line.strip()
            if line:
                names.add(line)

    add_lines(git_output(["diff", "--name-only", f"{base}...{head}"]))

    if include_working_tree:
        add_lines(git_output(["diff", "--name-only"]))
        add_lines(git_output(["diff", "--cached", "--name-only"]))
        add_lines(git_output(["ls-files", "--others", "--exclude-standard"]))

    return sorted(names)


def is_text_file(path):
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {
        "README",
        "README.md",
        ".gitignore",
    }


def add_error(errors, relative, message):
    errors.append(f"{relative}: {message}")


def check_path_policy(relative, errors):
    normalized = relative.replace("\\", "/")
    name = Path(normalized).name.lower()

    if name in RUNTIME_BASENAMES:
        add_error(
            errors,
            relative,
            "runtime/generated JSON must not be included in a PR",
        )

    if any(normalized.startswith(prefix) for prefix in RUNTIME_PREFIXES):
        add_error(
            errors,
            relative,
            "runtime photos/logs must not be included in a PR",
        )

    if any(token in name for token in OBSOLETE_LOCAL_EVENT_NAMES):
        add_error(
            errors,
            relative,
            "obsolete Local Event overlay file is blocked",
        )

    if ".bak" in name or name.endswith(".back"):
        add_error(
            errors,
            relative,
            "backup file must not be committed",
        )


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

    if relative == "index.html":
        lowered = text.lower()

        for token in FORBIDDEN_UI_TEXT:
            if token in lowered:
                add_error(
                    errors,
                    relative,
                    f'blocked UI content detected: "{token}"',
                )

        for token in OBSOLETE_LOCAL_EVENT_NAMES:
            if token in lowered:
                add_error(
                    errors,
                    relative,
                    f"obsolete Local Event layer reference detected: {token}",
                )

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
    for relative in filter(None, raw.split("\0")):
        path = ROOT / relative
        if not path.is_file():
            continue

        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            add_error(errors, relative, f"Python syntax error: {exc.msg}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--include-working-tree", action="store_true")
    args = parser.parse_args()

    errors = []
    paths = changed_paths(
        args.base,
        args.head,
        args.include_working_tree,
    )

    for relative in paths:
        check_path_policy(relative, errors)

        path = ROOT / relative
        if not path.is_file():
            continue

        if path.suffix.lower() == ".json":
            check_json(relative, path, errors)

        if not is_text_file(path):
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        check_text_content(relative, text, errors)

    check_python_syntax(errors)

    if errors:
        print("QUALITY GATE FAILED")
        for error in errors:
            print(f" - {error}")
        return 1

    print(f"QUALITY GATE PASSED ({len(paths)} changed file(s) inspected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
