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


def test_shell_scripts_parse_with_bash_noexec() -> None:
    for relative in SHELL_SCRIPTS:
        path = ROOT / relative
        assert path.exists(), relative
        subprocess.run(["bash", "-n", str(path)], cwd=ROOT, check=True, capture_output=True, text=True)


def test_full_ci_script_collects_agent_accessible_logs() -> None:
    script = read_text("scripts/run_full_ci_tests.sh")

    assert "ACCEPTANCE_ARTIFACT_DIR" in script
    assert "summary.md" in script
    assert "pytest-junit.xml" in script
    assert "openapi.json" in script
    assert "report.json" in script
    assert "cat \"$SUMMARY\"" in script


def test_full_ci_script_runs_closed_loop_fixture_data() -> None:
    script = read_text("scripts/run_full_ci_tests.sh")

    assert "tests/fixtures/runtime_data" in script
    assert "seed_runtime_data" in script
    assert "INFOSCREEN_ENV_DIR" in script
    assert "fixture-photo.txt" in script


def test_full_ci_script_runs_repository_hygiene_checker() -> None:
    script = read_text("scripts/run_full_ci_tests.sh")

    assert "scripts/ci/check_repo.py" in script
    assert "--suite all" in script
    assert "--scope repository" in script


def test_readme_uses_canonical_surface_operator_entrypoints() -> None:
    readme = read_text("README.md")

    assert "bash deploy/scripts/install-user-systemd.sh" in readme
    assert "bash scripts/infoscreen_status.sh" in readme
    assert "scripts/setup_surface_go.sh" not in readme


def test_mac_schedule_sync_uses_local_config_and_runtime_target() -> None:
    sync_script = read_text("mac/sync_schedule.sh")
    setup_script = read_text("mac/scripts/setup-schedule-sync.sh")

    assert "CONFIG_FILE=\"$SCRIPT_DIR/local.env\"" in sync_script
    assert "source \"$CONFIG_FILE\"" in sync_script
    assert "SURFACE_HOST:?SURFACE_HOST is required" in sync_script
    assert "~/infoscreen/surface/.env/schedule.json" in sync_script
    assert "mkdir -p $REMOTE_DIR" in sync_script
    assert "scp -q" in sync_script
    assert "${REMOTE_SCHEDULE_JSON:-~/infoscreen/surface/.env/schedule.json}" in setup_script
    assert "~/infoscreen/schedule.json" not in sync_script
    assert "~/infoscreen/schedule.json" not in setup_script
    assert "/home/rody/infoscreen/schedule.json" not in sync_script
    assert "/home/rody/infoscreen/schedule.json" not in setup_script


def test_document_roles_are_distinct() -> None:
    readme = read_text("README.md")
    design = read_text("docs/design.md")
    api = read_text("docs/api-spec.md")
    decisions = read_text("docs/questions.md")

    assert readme.startswith("# InfoScreen\n")
    assert design.startswith("# InfoScreen system architecture")
    assert api.startswith("# InfoScreen HTTP interaction contract")
    assert decisions.startswith("# InfoScreen project discussion and decision record")

    assert "## 1. What the project provides" in readme
    assert "## 3. Data sources, producers, and page consumers" in readme
    assert "## 8. Deployment and update" in readme
    assert "## 9. Operation and troubleshooting" in readme
    assert "## 10. Development and validation" in readme
    assert "## 8. Source-specific Local Events architecture" in design
    assert "## 5. Market configuration interaction" in api
    assert "## Decision record 018" in decisions

    assert "operator runbook" not in readme
    assert "Browser renderer ownership" not in readme
    assert "Repository root policy" not in readme
    assert "sudo apt" not in design
    assert "systemctl --user restart" not in design
    assert "systemctl" not in decisions
    assert "python3 -m pytest" not in decisions


def test_readme_covers_project_data_interaction_refresh_deployment_and_recovery() -> None:
    readme = read_text("README.md")

    required = [
        "## 1. What the project provides",
        "## 2. Product and runtime model",
        "## 3. Data sources, producers, and page consumers",
        "## 4. User interaction and configuration",
        "## 5. Refresh behaviour",
        "## 6. Local Events is source-specific by design",
        "## 7. Project structure",
        "## 8. Deployment and update",
        "## 9. Operation and troubleshooting",
        "## 10. Development and validation",
        "## 11. Documentation",
        "infoscreen-live-data.timer",
        "infoscreen-event-stream.timer",
        "infoscreen-local-events.timer",
        "local_event_search_results.partial.json",
        "debug_by_source",
        "market_config.default.json",
        "mac/local.env",
        "Last-Modified",
        "rendered_dom_card",
        "positive event intent",
        "Gardens by the Bay",
        "Mandai",
    ]
    for value in required:
        assert value in readme


def test_design_documents_sources_refresh_layers_and_targeted_local_events() -> None:
    design = read_text("docs/design.md")

    required = [
        "## 4. Three refresh layers",
        "### 4.1 Producer refresh",
        "### 4.2 Browser data reload",
        "### 4.3 Visual rotation",
        "## 5. UI ownership, interaction, and data source map",
        "## 8. Source-specific Local Events architecture",
        "### 8.2 Source inventory and adapter choices",
        "### 8.3 Collection pipeline",
        "### 8.4 Positive event intent",
        "### 8.5 Targeted source behavior",
        "### 8.6 Crawl budgets and configuration",
        "### 8.7 Output, partial-run protection, and evidence",
        "Children's Museum Singapore",
        "National Gallery Singapore",
        "SAFRA",
        "One Punggol",
        "Waterway Point",
        "Mandai Wildlife Group",
        "Sentosa",
        "Gardens by the Bay",
        "rendered_dom_card",
        "`nhb`",
        "Nasdaq",
        "Open-Meteo",
        "Google News",
        "macOS Calendar/EventKit",
        "local_event_search_results.partial.json",
    ]
    for value in required:
        assert value in design


def test_api_spec_documents_callers_payloads_and_side_effects() -> None:
    api = read_text("docs/api-spec.md")

    required = [
        "## 3. Runtime JSON reads",
        "### HEAD freshness contract",
        "## 5. Market configuration interaction",
        "POST /api/market-config",
        "## 6. Market and Weather manual refresh",
        "POST /api/market-refresh",
        "## 7. Local Events read interaction",
        "GET /api/local-events/search",
        "## 8. Local Events search interaction",
        "POST /api/local-events/search",
        '"location": "Punggol Singapore"',
        "source-specific official collector",
        "local_event_search_results.partial.json",
        "## 9. Browser interaction summary",
        "0.0.0.0:8765",
    ]
    for value in required:
        assert value in api


def test_questions_is_an_english_discussion_decision_record() -> None:
    decisions = read_text("docs/questions.md")

    assert decisions.count("## Decision record ") >= 18
    assert decisions.count("**Discussion context**") >= 18
    assert decisions.count("**Decision**") >= 18
    assert decisions.count("**Why this direction was chosen**") >= 18
    assert decisions.count("**Resulting implementation**") >= 18

    assert "Decision record 010 — Build Local Events from curated official sources" in decisions
    assert "Decision record 011 — Develop Local Events with shared stages plus source-specific adapters" in decisions
    assert "Decision record 012 — Require positive evidence that a record is an event" in decisions
    assert "Decision record 018 — Keep README as the project entrypoint and separate specialist documents" in decisions
    assert "The project overview and entrypoint belong in `README.md`" in decisions

    assert re.search(r"[\u3400-\u9fff]", decisions) is None
    assert re.search(r"^##\s+(What|Where|Which|How|Why)\b", decisions, re.MULTILINE) is None

    forbidden_incident_phrases = [
        "the assistant made",
        "previous response",
        "we fixed the mistake",
        "GitHub Actions did not run",
        "pytest was not executed",
    ]
    for value in forbidden_incident_phrases:
        assert value not in decisions


def test_schedule_sync_is_documented_across_project_architecture_and_decisions() -> None:
    readme = read_text("README.md")
    design = read_text("docs/design.md")
    decisions = read_text("docs/questions.md")

    assert "bash mac/scripts/setup-schedule-sync.sh" in readme
    assert "--host <surface-ip-or-hostname>" in readme
    assert "~/infoscreen/surface/.env/schedule.json" in readme
    assert "## 9. Calendar pipeline" in design
    assert "mac/sync_schedule.sh" in design
    assert "Decision record 002 — Separate the Surface runtime from the Mac Calendar authority" in decisions


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


def test_ci_workflow_runs_full_tests_without_uploading_artifacts() -> None:
    workflow = read_text(".github/workflows/acceptance.yml")

    assert "bash scripts/run_full_ci_tests.sh" in workflow
    assert "ACCEPTANCE_ARTIFACT_DIR" in workflow
    assert "pydantic" in workflow
    assert "pytest" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "Upload acceptance artifacts" not in workflow
