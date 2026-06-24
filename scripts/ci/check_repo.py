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

# Match only actual Git conflict-marker lines. Quoted strings containing these
# characters in the checker itself are not conflicts.
CONFLICT_RE = re.compile(
    r"^(?:<{7}[^\n]*|={7}|>{7}[^\n]*)$",
    re.MULTILINE,
)

SUITES = ("paths", "content", "structure", "python", "all")
SCOPES = ("changed", "repository")


def git_result(args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_output(args):
    result = git_result(args)
    if result.returncode != 0:
        raise RuntimeError(
            "git command failed: git " + " ".join(args) + "\n" + result.stderr
        )
    return result.stdout


def git_success(args):
    return git_result(args).returncode == 0


def split_null_output(text):
    return [item for item in text.split("\0") if item]


def diff_revision(base, head):
    """Return a diff revision that works for both related and unrelated refs."""
    if git_success(["merge-base", base, head]):
        return f"{base}...{head}"
    return f"{base}..{head}"


def parse_name_status(raw):
    """Parse `git diff --name-status -z` output into {status,path} dicts."""
    parts = split_null_output(raw)
    entries = []
    i = 0

    while i < len(parts):
        status = parts[i]
        i += 1
        code = status[:1]

        if code in {"R", "C"} and i + 1 < len(parts):
            # Rename/copy output is: status, old path, new path.
            i += 1
            path = parts[i]
            i += 1
        elif i < len(parts):
            path = parts[i]
            i += 1
        else:
            break

        entries.append({"status": code, "path": path})

    return entries


def merge_entries(*entry_lists):
    merged = {}
    priority = {"A": 5, "M": 4, "R": 4, "C": 4, "T": 3, "U": 3, "D": 1}

    for entries in entry_lists:
        for entry in entries:
            path = entry["path"]
            current = merged.get(path)
            if current is None:
                merged[path] = entry
                continue

            if priority.get(entry["status"], 2) >= priority.get(current["status"], 2):
                merged[path] = entry

    return [merged[path] for path in sorted(merged)]


def changed_entries(base, head, include_working_tree):
    revision = diff_revision(base, head)
    entries = parse_name_status(git_output([
        "diff",
        "--name-status",
        "-z",
        revision,
    ]))

    extra = []
    if include_working_tree:
        extra.extend(parse_name_status(git_output([
            "diff",
            "--name-status",
            "-z",
        ])))
        extra.extend(parse_name_status(git_output([
            "diff",
            "--cached",
            "--name-status",
            "-z",
        ])))
        extra.extend({"status": "A", "path": item} for item in split_null_output(git_output([
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ])))

    return merge_entries(entries, extra)


def repository_entries(include_working_tree):
    entries = [
        {"status": "A", "path": item}
        for item in split_null_output(git_output(["ls-files", "-z"]))
    ]

    if include_working_tree:
        entries.extend(
            {"status": "A", "path": item}
            for item in split_null_output(git_output([
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ]))
        )

    return merge_entries(entries)


def selected_entries(args):
    if args.scope == "repository":
        return repository_entries(args.include_working_tree)

    if not args.base:
        raise ValueError("--base is required when --scope changed is selected")

    return changed_entries(args.base, args.head, args.include_working_tree)


def entry_paths(entries):
    return sorted({entry["path"] for entry in entries})


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


def run_paths_suite(entries, errors):
    for entry in entries:
        # Deleting a blocked runtime/generated file is allowed. Only additions,
        # modifications, renames, copies, and unresolved changes should be blocked.
        if entry["status"] == "D":
            continue
        check_path_policy(entry["path"], errors)


def run_content_suite(paths, errors):
    for relative in paths:
        path = ROOT / relative
        if not path.is_file() or not is_text_file(path):
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        check_text_content(relative, text, errors)


def run_structure_suite(paths, errors):
    for relative in paths:
        path = ROOT / relative
        if not path.is_file():
            continue

        if path.suffix.lower() == ".json":
            check_json(relative, path, errors)

        if relative == "index.html":
            check_html_structure(
                relative,
                path.read_text(encoding="utf-8", errors="replace"),
                errors,
            )


def run_suite(name, entries, paths, errors):
    if name in ("paths", "all"):
        run_paths_suite(entries, errors)

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
        entries = selected_entries(args)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    paths = entry_paths(entries)
    errors = []
    run_suite(args.suite, entries, paths, errors)

    if errors:
        print(f"FAILED suite={args.suite} scope={args.scope}")
        for error in errors:
            print(f" - {error}")
        return 1

    print(
        f"PASSED suite={args.suite} scope={args.scope} "
        f"files={len(paths)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
