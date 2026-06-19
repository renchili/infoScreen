from __future__ import annotations

import subprocess
from pathlib import Path


GENERATED_PLIST = "mac/com.renchi.infoscreen.schedule-sync.plist"
INSTALLER = Path("mac/install_schedule_sync.sh")


def git_ls_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        text=True,
        capture_output=True,
    )
    return set(result.stdout.splitlines())


def test_launchd_plist_is_generated_not_tracked() -> None:
    tracked = git_ls_files()

    assert GENERATED_PLIST not in tracked
    assert INSTALLER.is_file()


def test_launchd_installer_generates_runtime_plist() -> None:
    text = INSTALLER.read_text(encoding="utf-8")

    required = [
        "SCRIPT_DIR=",
        "REPO_ROOT=",
        "LAUNCH_AGENT_DIR=",
        "Library/LaunchAgents",
        "launchctl bootstrap",
        "plutil -lint",
        "find_sync_script",
    ]

    missing = [item for item in required if item not in text]
    assert not missing, f"installer missing required behavior: {missing}"

    private_mac_home = "/".join(("", "Users", "rody"))
    private_surface_home = "/".join(("", "home", "rody"))

    forbidden = [
        private_mac_home,
        private_surface_home,
        "__MAC_HOME__",
        "__INFOSCREEN_REPO__",
        "__SURFACE_HOME__",
    ]

    present = [item for item in forbidden if item in text]
    assert not present, f"installer must not contain hardcoded/private placeholders: {present}"
