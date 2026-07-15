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


def test_schedule_sync_operator_documentation_is_discoverable() -> None:
    readme = read_text("README.md")
    design = read_text("docs/design.md")
    questions = read_text("docs/questions.md")

    assert "Schedule sync — run on the Mac" in readme
    assert "macOS Calendar/EventKit is the data source" in readme
    assert "bash mac/scripts/setup-schedule-sync.sh" in readme
    assert "--host <surface-ip-or-hostname>" in readme
    assert "mac/local.env" in readme
    assert "~/infoscreen/surface/.env/schedule.json" in readme
    assert "Mac Calendar/EventKit" in design
    assert "mac/sync_schedule.sh" in design
    assert "surface/.env/schedule.json" in design
    assert "日程的权威来源是 Mac 上的 macOS Calendar/EventKit" in questions
    assert "Surface 只保存、提供 HTTP 访问并渲染日程" in questions


def test_page_ui_job_and_source_mapping_is_documented() -> None:
    readme = read_text("README.md")
    design = read_text("docs/design.md")

    required_readme = [
        "Page UI, jobs, and data sources",
        "Market card",
        "Global market tape",
        "Local event card",
        "Sync ticker",
        "EN/FR/中文 news ticker",
        "Photo wall",
        "Weather card",
        "CPU/MEM/DSK/NET bars",
        "Calendar board",
        "POWER/DISPLAY/NETWORK labels",
        "OpenAPI pages",
        "infoscreen-local-events.timer",
        "surface/conf/event_sources.json",
        "Open-Meteo",
        "Nasdaq, CNBC, Stooq",
        "`Math.random()` demo values",
    ]
    for value in required_readme:
        assert value in readme

    required_design = [
        "Page UI ownership and data sources",
        "Browser renderer ownership",
        "infoscreen-http.service",
        "infoscreen-live-data.timer",
        "infoscreen-event-stream.timer",
        "infoscreen-local-events.timer",
        "Mac LaunchAgent",
        "Simulated and static UI contract",
        "local_event_card.js photo renderer",
        "dashboard.js + sync ticker",
    ]
    for value in required_design:
        assert value in design


def test_questions_only_records_durable_product_decisions() -> None:
    questions = read_text("docs/questions.md")

    required = [
        "InfoScreen 的运行边界是什么",
        "运行时数据和个人数据放在哪里",
        "日程数据从哪里来",
        "本地活动允许使用哪些来源",
        "什么内容才算本地活动",
        "本地活动的数据质量由哪一层负责",
        "本地活动按什么顺序展示",
    ]
    for value in required:
        assert value in questions

    forbidden = [
        "GitHub Actions 关闭时怎么验收",
        "为什么默认不上传测试 artifact",
        "仓库卫生为什么不做成一堆产品单元测试",
        "同步状态异常时怎么处理",
        "Market 为什么只能有一个渲染 owner",
        "左侧同步状态分别对应什么任务、产物和界面",
    ]
    for value in forbidden:
        assert value not in questions


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
