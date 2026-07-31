from __future__ import annotations

from .conftest import read_text


def test_launchagent_persists_schedule_configuration_as_arguments() -> None:
    setup = read_text("mac/scripts/setup-schedule-sync.sh")

    for value in [
        '"ProgramArguments": [',
        '"--python"',
        '"--surface-host"',
        '"--surface-user"',
        '"--remote-path"',
        '"--local-json"',
        '"--log-dir"',
        "Runtime configuration is stored in LaunchAgent ProgramArguments.",
    ]:
        assert value in setup

    assert '} > "$CONFIG_FILE"' not in setup
    assert "printf 'SURFACE_HOST=" not in setup
    assert "printf 'REMOTE_SCHEDULE_JSON=" not in setup


def test_schedule_sync_accepts_explicit_arguments_and_absolute_remote_path() -> None:
    sync = read_text("mac/sync_schedule.sh")

    for value in [
        "--surface-host|--host",
        "--surface-user|--user",
        "--remote-path",
        "--python",
        "--local-json",
        "--log-dir",
        'case "$REMOTE_SCHEDULE_JSON" in',
        "/*)",
        '"~/"*)',
        'REMOTE_TMP_RELATIVE="${REMOTE_RELATIVE_JSON}.tmp.$$"',
        'scp -q "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON"',
        "verify published schedule",
    ]:
        assert value in sync

    assert "Command-line arguments are the authoritative runtime configuration" in sync
