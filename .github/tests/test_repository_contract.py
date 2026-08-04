from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.scripts

SHELL_SCRIPTS = [
    ".github/scripts/run_acceptance.sh",
    ".github/scripts/run_full_ci_tests.sh",
    ".github/scripts/run_pre_pr.sh",
    ".github/scripts/check_shell_syntax.sh",
    ".github/scripts/check_javascript_syntax.sh",
    "surface/deploy/install-user-systemd.sh",
    "surface/scripts/infoscreen_status.sh",
    "surface/scripts/restart_kiosk.sh",
    "mac/sync_schedule.sh",
    "mac/scripts/setup-schedule-sync.sh",
]

QUESTIONS_SECTIONS = [
    "Easy-to-make interpretation",
    "Why it fails",
    "Correct requirement interpretation",
    "Required implementation",
    "Acceptance evidence",
]


def read_text(path: str | Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shell_scripts_parse_with_bash_noexec() -> None:
    for relative in SHELL_SCRIPTS:
        path = ROOT / relative
        assert path.exists(), relative
        subprocess.run(
            ["bash", "-n", str(path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


def test_repository_root_has_device_owned_layout() -> None:
    forbidden = ["deploy", "scripts", "tests", "pyproject.toml"]
    for relative in forbidden:
        assert not (ROOT / relative).exists(), relative

    required = [
        "surface/deploy/install-user-systemd.sh",
        "surface/deploy/systemd/user/infoscreen-http.service",
        "surface/scripts/infoscreen_status.sh",
        "surface/scripts/collect_local_event_preview.py",
        "surface/tests/conftest.py",
        "surface/tests/test_local_event_review_expiry.py",
        "mac/tests/test_schedule_sync_arguments_contract.py",
        ".github/pytest.ini",
        ".github/scripts/run_full_ci_tests.sh",
        ".github/tests/test_repository_contract.py",
    ]
    for relative in required:
        assert (ROOT / relative).exists(), relative


def test_javascript_syntax_checker_uses_tracked_html_pages() -> None:
    script = read_text(".github/scripts/check_javascript_syntax.sh")

    assert "git ls-files -z -- '*.html'" in script
    assert ".github/scripts/extract_inline_js.py" in script
    assert '"$html"' in script
    assert '"$TEMP_DIR/inline-js-$html_index"' in script


def test_full_ci_script_collects_agent_accessible_outputs() -> None:
    script = read_text(".github/scripts/run_full_ci_tests.sh")

    for value in [
        "ACCEPTANCE_ARTIFACT_DIR",
        "summary.md",
        "pytest-junit.xml",
        "openapi.json",
        "report.json",
        'cat "$SUMMARY"',
        "surface/tests/fixtures/runtime_data",
        ".github/scripts/check_repo.py",
        "python3 -m pytest -c .github/pytest.ini",
    ]:
        assert value in script


def test_readme_uses_device_owned_operator_entrypoints() -> None:
    readme = read_text("README.md")

    for value in [
        "bash surface/deploy/install-user-systemd.sh",
        "bash surface/scripts/infoscreen_status.sh",
        "bash .github/scripts/run_full_ci_tests.sh",
        "surface/tests/",
        "mac/tests/",
        ".github/pytest.ini",
        "git switch main",
        "git pull --ff-only origin main",
    ]:
        assert value in readme

    for value in [
        "bash deploy/scripts/install-user-systemd.sh",
        "bash scripts/infoscreen_status.sh",
        "bash scripts/run_full_ci_tests.sh",
        "\ndeploy/",
        "\nscripts/",
        "\ntests/",
        "\npyproject.toml",
    ]:
        assert value not in readme


def test_readme_follows_operator_reading_order() -> None:
    readme = read_text("README.md")

    ordered = [
        "## 1. Project overview",
        "## 2. Start the project",
        "## 3. Pages and their relationship",
        "## 4. Data and page flow",
        "## 5. Feature guide",
        "## 6. Configuration and runtime data",
        "## 7. Common operations",
        "## 8. Troubleshooting",
        "## 9. Project structure",
        "## 10. Development and documentation",
    ]
    positions = [readme.index(heading) for heading in ordered]
    assert positions == sorted(positions)


def test_agent_is_project_specialization_not_tree_circularity() -> None:
    bootstrap = read_text("AGENTS.md")
    rules = read_text("AGENT.md")

    assert "InfoScreen-specialized form" in bootstrap
    assert "current file tree is evidence" in bootstrap
    assert "InfoScreen-specific specialization of `AGENTS.md`" in rules
    assert "Top-level organization follows runtime and platform ownership" in rules
    assert "surface/local_events_runtime/" in rules
    assert "Do not create a duplicate `surface/jobs/local_events/` implementation" in rules

    root_policy = rules.split("## Repository root policy", 1)[1]
    intended_root = root_policy.split("```text", 1)[1].split("```", 1)[0]
    for value in ["deploy/", "scripts/", "tests/", "pyproject.toml"]:
        assert value not in intended_root


def test_mac_schedule_sync_uses_atomic_remote_publish() -> None:
    sync_script = read_text("mac/sync_schedule.sh")
    setup_script = read_text("mac/scripts/setup-schedule-sync.sh")

    for value in [
        "--surface-host|--host",
        "--surface-user|--user",
        "--remote-path",
        'REMOTE_TMP_RELATIVE="${REMOTE_RELATIVE_JSON}.tmp.$$"',
        'scp -q "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON"',
        "verify published schedule",
    ]:
        assert value in sync_script

    for value in [
        '"ProgramArguments": [',
        '"--surface-host"',
        '"--surface-user"',
        '"--remote-path"',
    ]:
        assert value in setup_script


def test_document_roles_are_distinct() -> None:
    readme = read_text("README.md")
    design = read_text("docs/design.md")
    api = read_text("docs/api-spec.md")
    explanations = read_text("docs/questions.md")

    assert readme.startswith("# InfoScreen\n")
    assert design.startswith("# InfoScreen system architecture")
    assert api.startswith("# InfoScreen HTTP interaction contract")
    assert explanations.startswith("# InfoScreen requirement clarifications")

    assert "## 2. Start the project" in readme
    assert "## 6. Source-specific Local Events architecture" in design
    assert "## 5. Market configuration interaction" in api
    assert "## Validation boundaries" in explanations


def test_documented_paths_and_runtime_boundaries_match_current_owners() -> None:
    readme = read_text("README.md")
    design = read_text("docs/design.md")
    api = read_text("docs/api-spec.md")
    questions = read_text("docs/questions.md")
    openapi = read_text("surface/openapi_spec.py")
    handoff = read_text(
        "surface/local_events_runtime/preview_final_detail_handoff_authority.py"
    )
    direct_preview = read_text(
        "surface/local_events_runtime/preview_direct_detail_collector_authority.py"
    )
    archive = read_text(
        "surface/local_events_runtime/listing_page_archive_authority.py"
    )
    dashboard = read_text("surface/web/assets/js/dashboard.js")
    index = read_text("surface/web/index.html")

    assert "`scripts/infoscreen_status.sh`" not in questions
    assert "`surface/scripts/infoscreen_status.sh`" in questions

    for document in (design, api, questions):
        assert "preview_expiry_policy" in document
        assert "retain_for_operator_review" in document
        assert "normal expiry" in document

    assert '"preview_expiry_policy": "retain_for_operator_review"' in handoff
    assert "exclude_ended_events" not in handoff
    assert "_retain_expired_preview_events" in handoff

    for document in (design, api, questions, openapi):
        assert "same_browser_context" in document
        assert "sequential_browser_processes" in document
        assert "single_playwright_sequential_browsers" in document

    for value in [
        '"preview_detail_transport": (',
        '"sequential_browser_processes"',
        '"same_browser_context"',
        '"single_playwright_sequential_browsers"',
        '1 + fresh_detail_browsers',
    ]:
        assert value in direct_preview

    assert "_selection._confirmed_selections = _confirmed_selections" in archive
    assert "no current confirmed List Page" in archive
    for document in (design, api, questions, openapi):
        lowered = document.casefold()
        assert "archive" in lowered
        assert "formal" in lowered

    assert "browser-generated demo values" in readme
    assert "static kiosk labels" in readme
    assert "function updateDemoMetrics()" in dashboard
    assert "Math.random()" in dashboard
    for label in ("POWER", "DISPLAY", "NETWORK"):
        assert f'<div class="stat-label">{label}</div>' in index


def test_documented_systemd_job_cadence_matches_units() -> None:
    live_service = read_text(
        "surface/deploy/systemd/user/infoscreen-live-data.service"
    )
    live_timer = read_text(
        "surface/deploy/systemd/user/infoscreen-live-data.timer"
    )
    news_service = read_text(
        "surface/deploy/systemd/user/infoscreen-event-stream.service"
    )
    news_timer = read_text(
        "surface/deploy/systemd/user/infoscreen-event-stream.timer"
    )
    local_service = read_text(
        "surface/deploy/systemd/user/infoscreen-local-events.service"
    )
    local_timer = read_text(
        "surface/deploy/systemd/user/infoscreen-local-events.timer"
    )

    assert "surface/fetch_live_data.py" in live_service
    assert "OnUnitActiveSec=5min" in live_timer
    assert "surface/fetch_event_stream.py" in news_service
    assert "OnUnitActiveSec=5min" in news_timer
    assert "surface/search_local_events.py Punggol Singapore" in local_service
    assert "OnUnitActiveSec=6h" in local_timer


def test_ci_workflows_use_ci_owned_entrypoints() -> None:
    workflows = [
        ".github/workflows/acceptance.yml",
        ".github/workflows/pre-pr.yml",
        ".github/workflows/quality-gate.yml",
        ".github/workflows/post-merge.yml",
    ]

    for path in workflows:
        workflow = read_text(path)
        assert "github.run_attempt" in workflow
        assert "Re-runs are blocked" in workflow
        assert "concurrency:" in workflow
        assert "cancel-in-progress: true" in workflow
        assert "scripts/ci/" not in workflow
        assert "bash scripts/" not in workflow

    assert "bash .github/scripts/run_full_ci_tests.sh" in read_text(
        ".github/workflows/acceptance.yml"
    )
    assert ".github/scripts/check_repo.py" in read_text(
        ".github/workflows/pre-pr.yml"
    )


def test_questions_follow_mandatory_clarification_structure() -> None:
    explanations = read_text("docs/questions.md")
    topic_blocks = re.split(r"(?m)^## ", explanations)[1:]

    for block in topic_blocks:
        subheadings = re.findall(r"(?m)^### (.+)$", block)
        assert subheadings == QUESTIONS_SECTIONS
        for index, heading in enumerate(QUESTIONS_SECTIONS):
            start = block.index(f"### {heading}\n") + len(f"### {heading}\n")
            end = (
                block.index(f"### {QUESTIONS_SECTIONS[index + 1]}\n", start)
                if index + 1 < len(QUESTIONS_SECTIONS)
                else len(block)
            )
            assert block[start:end].strip()
