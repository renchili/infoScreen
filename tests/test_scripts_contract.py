from __future__ import annotations

import re
import subprocess

import pytest

from .conftest import ROOT, read_text

pytestmark = pytest.mark.scripts


SHELL_SCRIPTS = [
    "scripts/run_acceptance.sh",
    "scripts/run_full_ci_tests.sh",
    "scripts/infoscreen_status.sh",
    "scripts/setup_surface_go.sh",
    "deploy/scripts/install-user-systemd.sh",
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


def test_javascript_syntax_checker_uses_tracked_html_pages() -> None:
    script = read_text("scripts/ci/check_javascript_syntax.sh")

    assert "git ls-files -z -- '*.html'" in script
    assert "scripts/ci/extract_inline_js.py" in script
    assert '"$html"' in script
    assert '"$TEMP_DIR/inline-js-$html_index"' in script
    assert "extract_inline_js.py index.html" not in script


def test_full_ci_script_collects_agent_accessible_outputs() -> None:
    script = read_text("scripts/run_full_ci_tests.sh")

    for value in [
        "ACCEPTANCE_ARTIFACT_DIR",
        "summary.md",
        "pytest-junit.xml",
        "openapi.json",
        "report.json",
        'cat "$SUMMARY"',
    ]:
        assert value in script


def test_full_ci_script_runs_closed_loop_fixture_data_and_repo_guard() -> None:
    script = read_text("scripts/run_full_ci_tests.sh")

    for value in [
        "tests/fixtures/runtime_data",
        "seed_runtime_data",
        "INFOSCREEN_ENV_DIR",
        "fixture-photo.txt",
        "scripts/ci/check_repo.py",
        "--suite all",
        "--scope repository",
    ]:
        assert value in script


def test_readme_uses_canonical_main_operator_entrypoints() -> None:
    readme = read_text("README.md")

    assert "bash deploy/scripts/install-user-systemd.sh" in readme
    assert "bash scripts/infoscreen_status.sh" in readme
    assert "git switch main" in readme
    assert "git pull --ff-only origin main" in readme
    assert "develop/surface-local-events-coverage" not in readme
    assert "scripts/setup_surface_go.sh" not in readme


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

    for value in [
        "python3 surface/serve_infoscreen.py",
        "http://127.0.0.1:8765/",
        "http://127.0.0.1:8765/local-events/studio/",
        "http://127.0.0.1:8765/docs",
        "surface/.env/",
        "surface/local_events_runtime/",
    ]:
        assert value in readme


def test_agent_declares_canonical_local_event_package_and_output_boundary() -> None:
    rules = read_text("AGENT.md")

    assert "surface/local_events_runtime/" in rules
    assert "Do not create a duplicate `surface/jobs/local_events/` implementation" in rules
    assert "surface/jobs/local_event_search.py" in rules
    assert "## Logging and command-output model" in rules
    assert "final JSON payload to stdout" in rules


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

    assert "~/infoscreen/schedule.json" not in sync_script


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
    assert "## 3. Pages and their relationship" in readme
    assert "## 5. Feature guide" in readme
    assert "## 6. Source-specific Local Events architecture" in design
    assert "## 5. Market configuration interaction" in api
    assert "## Visual language" in explanations
    assert "## Validation boundaries" in explanations

    assert "--disable-http2" not in readme
    assert "preview_browser_process_count" not in readme
    assert "### Acceptance evidence" not in readme
    assert "sudo apt" not in design
    assert "systemctl" not in explanations
    assert "python3 -m pytest" not in explanations


def test_readme_covers_startup_pages_features_and_operations() -> None:
    readme = read_text("README.md")

    required = [
        "## 1. Project overview",
        "## 2. Start the project",
        "## 3. Pages and their relationship",
        "## 4. Data and page flow",
        "## 5. Feature guide",
        "## 6. Configuration and runtime data",
        "## 7. Common operations",
        "## 8. Troubleshooting",
        "### 3.1 Dashboard",
        "### 3.2 Local Event Studio",
        "### 3.3 API documentation",
        "### 5.6 Calendar and Schedule sync",
        "### 5.7 Photos",
        "infoscreen-live-data.timer",
        "infoscreen-event-stream.timer",
        "infoscreen-local-events.timer",
        "mac/scripts/setup-schedule-sync.sh",
        "python3 surface/build_photos_json.py",
        "market_config.default.json",
        "local_event_search_results.json",
    ]
    for value in required:
        assert value in readme


def test_design_documents_current_ownership_and_review_projection() -> None:
    design = read_text("docs/design.md")

    required = [
        "## 4. Refresh layers",
        "## 5. UI ownership",
        "## 6. Source-specific Local Events architecture",
        "### 6.2 Collection pipeline",
        "### 6.3 HTTP protocol policy",
        "### 6.4 Positive Event intent",
        "### 6.5 Detail-page authority",
        "## 7. Operator review state and kiosk projection",
        "### 7.2 Manual correct-list-page flow",
        "### 7.3 Zero-result diagnostics",
        "## 9. Local Events output protection",
        "local_event_collector_results.json",
        "local_event_search_results.partial.json",
        "--disable-http2",
    ]
    for value in required:
        assert value in design


def test_api_spec_documents_current_routes_and_side_effects() -> None:
    api = read_text("docs/api-spec.md")

    required = [
        "## 3. Runtime JSON reads",
        "### HEAD freshness contract",
        "## 5. Market configuration interaction",
        "POST /api/market-config",
        "## 6. Market and Weather manual refresh",
        "POST /api/market-refresh",
        "## 7. Local Events read and dashboard-filter interaction",
        "GET /api/local-events/search",
        "## 8. Explicit Local Events collection interaction",
        "POST /api/local-events/search",
        '"location": "Punggol Singapore"',
        "source-specific official collector",
        "local_event_collector_results.json",
        "## 9. Local Event review interaction",
        "POST /api/local-events/review/listing-page",
        "POST /api/local-events/review/collect-events",
        "## 10. Browser interaction summary",
        "0.0.0.0:8765",
    ]
    for value in required:
        assert value in api


def test_questions_follow_mandatory_clarification_structure() -> None:
    explanations = read_text("docs/questions.md")
    topic_blocks = re.split(r"(?m)^## ", explanations)[1:]

    expected_topics = [
        "Visual language",
        "Calendar authority and unattended sync",
        "Runtime freshness and refresh layers",
        "Local Events source-specific collection",
        "Local Events listing-date authority",
        "Local Events manual correct-list-page entry",
        "Local Events positive Event intent",
        "Local Events zero-result diagnostics",
        "Local Events HTTP/2 handling",
        "Generated helper and archive boundary",
        "Local Events evidence and partial-result protection",
        "Local Events Review publication and kiosk authority",
        "Dashboard Local Events filtering and collection boundary",
        "Validation boundaries",
    ]
    assert [block.splitlines()[0].strip() for block in topic_blocks] == expected_topics

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

    for value in [
        "macOS Calendar/EventKit",
        "LaunchAgent `ProgramArguments`",
        "absolute remote path",
        "every seven seconds",
        "debug_by_source",
        "local_event_search_results.partial.json",
        "surface/local_events_runtime/",
        "partially verified",
    ]:
        assert value in explanations

    assert re.search(r"[\u3400-\u9fff]", explanations) is None
    assert re.search(r"(?m)^##\s+(Question|Answer|Q\d+)\b", explanations) is None
    assert "the assistant made" not in explanations
    assert "previous response" not in explanations


def test_documented_systemd_job_cadence_matches_units() -> None:
    live_service = read_text("deploy/systemd/user/infoscreen-live-data.service")
    live_timer = read_text("deploy/systemd/user/infoscreen-live-data.timer")
    news_service = read_text("deploy/systemd/user/infoscreen-event-stream.service")
    news_timer = read_text("deploy/systemd/user/infoscreen-event-stream.timer")
    local_service = read_text("deploy/systemd/user/infoscreen-local-events.service")
    local_timer = read_text("deploy/systemd/user/infoscreen-local-events.timer")

    assert "surface/fetch_live_data.py" in live_service
    assert "OnUnitActiveSec=5min" in live_timer
    assert "surface/fetch_event_stream.py" in news_service
    assert "OnUnitActiveSec=5min" in news_timer
    assert "surface/search_local_events.py Punggol Singapore" in local_service
    assert "OnUnitActiveSec=6h" in local_timer


def test_ci_workflow_defines_the_repository_acceptance_entrypoint() -> None:
    workflow = read_text(".github/workflows/acceptance.yml")

    assert "bash scripts/run_full_ci_tests.sh" in workflow
    assert "ACCEPTANCE_ARTIFACT_DIR" in workflow
    assert "pydantic" in workflow
    assert "pytest" in workflow


def test_workflows_reject_reruns_and_limit_branch_frequency() -> None:
    workflow_paths = [
        ".github/workflows/acceptance.yml",
        ".github/workflows/pre-pr.yml",
        ".github/workflows/quality-gate.yml",
        ".github/workflows/post-merge.yml",
    ]

    for path in workflow_paths:
        workflow = read_text(path)
        assert "github.run_attempt" in workflow
        assert "Re-runs are blocked" in workflow
        assert "concurrency:" in workflow
        assert "cancel-in-progress: true" in workflow

    for path in [
        ".github/workflows/acceptance.yml",
        ".github/workflows/pre-pr.yml",
        ".github/workflows/quality-gate.yml",
    ]:
        assert "sleep 90" in read_text(path)
