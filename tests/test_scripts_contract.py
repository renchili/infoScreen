from __future__ import annotations

import subprocess

import pytest

from .conftest import ROOT, read_text

pytestmark = pytest.mark.scripts


SHELL_SCRIPTS = [
    "scripts/run_acceptance.sh",
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


def test_acceptance_script_collects_agent_accessible_artifacts() -> None:
    script = read_text("scripts/run_acceptance.sh")

    assert "ACCEPTANCE_ARTIFACT_DIR" in script
    assert "summary.md" in script
    assert "pytest-junit.xml" in script
    assert "openapi.json" in script
    assert "server.log" in script
    assert "cat \"$SUMMARY\"" in script


def test_acceptance_script_runs_closed_loop_data_and_http_checks() -> None:
    script = read_text("scripts/run_acceptance.sh")

    assert "tests/fixtures/runtime_data" in script
    assert "seed_runtime_data" in script
    assert "ACCEPTANCE_START_SERVER" in script
    assert "http_market_fixture" in script
    assert "http_local_event_fixture" in script


def test_ci_workflow_runs_acceptance_and_uploads_artifacts() -> None:
    workflow = read_text(".github/workflows/acceptance.yml")

    assert "bash scripts/run_acceptance.sh" in workflow
    assert "ACCEPTANCE_START_SERVER" in workflow
    assert "actions/upload-artifact" in workflow
    assert "pydantic" in workflow
    assert "pytest" in workflow
