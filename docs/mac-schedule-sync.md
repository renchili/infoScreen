# macOS schedule sync

This repository keeps the dashboard schedule private. The Mac reads Apple Calendar through EventKit, writes `schedule.json`, and copies that one JSON file to the Surface/display host through SSH.

## Current Surface target

The current verified Surface target is:

```text
~/infoscreen/schedule.json
```

Do not change the Mac sync target to `~/infoscreen/surface/.env/schedule.json` unless the Surface server has first been changed and verified to read that path.

Before changing this path, verify the file currently served by the Surface host:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
```

## Prerequisites

- macOS with permission for the selected Python runtime to access Calendar.
- A Python runtime that can run `import EventKit`.
- SSH access to the display host.
- This repository cloned locally.

## Branch boundary

The Mac checkout does not need to switch to a Surface frontend/crawler branch to run schedule sync.

Schedule sync changes should be delivered as either:

```text
1. a mac-only patch touching mac/ and schedule-sync docs, or
2. a manual mac/local.env runtime configuration change
```

Do not mix Mac schedule-sync changes with Surface frontend, local-event crawler, or systemd/logging changes.

## Runtime config

The setup script creates a local-only file:

```text
mac/local.env
```

It must contain the current Surface target:

```text
REMOTE_SCHEDULE_JSON=~/infoscreen/schedule.json
```

If the file points to another path, fix `mac/local.env` before running the sync job.

## Install or update the sync job

From any directory inside the repository, run:

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/mac/scripts/setup-schedule-sync.sh" \
  --host "<ssh-host>" \
  --user "<ssh-user>" \
  --remote-path "~/infoscreen/schedule.json"
```

Optional arguments:

```text
--remote-path <remote-path>       Current default should be ~/infoscreen/schedule.json
--python <python-with-eventkit>   Select a specific Python runtime
--interval <seconds>              Default: 120
```

The setup script creates two machine-local files:

```text
mac/local.env
~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist
```

They contain local host, account, Python, remote path, and log settings. They are not committed to Git.

## Verify a manual sync

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/mac/sync_schedule.sh"
```

The generated JSON remains in `mac/schedule.json`; the script then copies it to the configured remote path.

On the Surface/display host, verify:

```bash
stat ~/infoscreen/schedule.json
head -n 40 ~/infoscreen/schedule.json
curl -s http://127.0.0.1:8765/schedule.json | python3 -m json.tool | head -n 40
```

## Check the macOS job

```bash
launchctl print "gui/$(id -u)/com.renchili.infoscreen.schedule-sync"
tail -n 80 "$HOME/Library/Logs/infoscreen-sync/push_schedule.log"
tail -n 80 "$HOME/Library/Logs/infoscreen-sync/launchd.err.log"
```

## Reconfigure

Run the setup command again with explicit arguments. It safely replaces the user LaunchAgent before loading the new one.

If `mac/local.env` points to `~/infoscreen/surface/.env/schedule.json`, edit it back to:

```text
REMOTE_SCHEDULE_JSON=~/infoscreen/schedule.json
```

## Remove the job

```bash
uid="$(id -u)"
label="com.renchili.infoscreen.schedule-sync"
plist="$HOME/Library/LaunchAgents/$label.plist"

launchctl bootout "gui/$uid/$label" 2>/dev/null || true
rm -f "$plist"
```

The legacy plist stored under `mac/launchagents/` is intentionally disabled and is not used by the setup command.
