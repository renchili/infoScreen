from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.scripts


def test_installer_preserves_conflicting_runtime_state() -> None:
    script = read_text("deploy/scripts/install-user-systemd.sh")

    assert 'MIGRATION_BACKUP_DIR="$SURFACE_ENV_DIR/migration_backup"' in script
    assert "preserve_legacy_path()" in script
    assert 'mv "$source" "$backup"' in script
    assert "no data was removed" in script
    assert 'rm -rf "$REPO_DIR/$name"' not in script


def test_installer_does_not_hide_required_unit_failures() -> None:
    script = read_text("deploy/scripts/install-user-systemd.sh")

    required_commands = [
        'cp "$REPO_DIR"/deploy/systemd/user/*.service "$SYSTEMD_USER_DIR"/',
        'cp "$REPO_DIR"/deploy/systemd/user/*.timer "$SYSTEMD_USER_DIR"/',
        "systemctl --user enable --now infoscreen-live-data.timer",
        "systemctl --user enable --now infoscreen-event-stream.timer",
        "systemctl --user enable --now infoscreen-local-events.timer",
        "systemctl --user start infoscreen-live-data.service",
        "systemctl --user start infoscreen-event-stream.service",
        "systemctl --user start --no-block infoscreen-local-events.service",
    ]
    for command in required_commands:
        assert command in script
        assert f"{command} 2>/dev/null || true" not in script
