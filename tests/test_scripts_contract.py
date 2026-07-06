from __future__ import annotations

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


def test_ci_workflow_runs_full_tests_without_uploading_artifacts() -> None:
    workflow = read_text(".github/workflows/acceptance.yml")

    assert "bash scripts/run_full_ci_tests.sh" in workflow
    assert "ACCEPTANCE_ARTIFACT_DIR" in workflow
    assert "pydantic" in workflow
    assert "pytest" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "Upload acceptance artifacts" not in workflow
