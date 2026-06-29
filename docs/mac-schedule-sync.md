# macOS schedule sync

This repository keeps the dashboard schedule private. The Mac reads Apple Calendar through EventKit, writes `schedule.json`, and copies that one JSON file to the display host through SSH.

The dashboard server reads the schedule from:

```text
~/infoscreen/surface/.env/schedule.json
```

Do not sync to the repository root `~/infoscreen/schedule.json`; the current server does not read that path.

## Prerequisites

- macOS with permission for the selected Python runtime to access Calendar.
- A Python runtime that can run `import EventKit`.
- SSH access to the display host.
- This repository cloned locally.

## Install or update the sync job

From any directory inside the repository, run:

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/mac/scripts/setup-schedule-sync.sh" \
  --host "<ssh-host>" \
  --user "<ssh-user>"
```

Optional arguments:

```text
--remote-path <remote-path>       Default: ~/infoscreen/surface/.env/schedule.json
--python <python-with-eventkit>   Select a specific Python runtime
--interval <seconds>              Default: 120
```

The setup script creates two machine-local files:

```text
mac/local.env
~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist
```

They contain local host, account, Python and log settings. They are not committed to Git.

## Verify a manual sync

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/mac/sync_schedule.sh"
```

The generated JSON remains in `mac/schedule.json`; the script then copies it to the configured remote path.

On the Surface/display host, verify:

```bash
stat ~/infoscreen/surface/.env/schedule.json
head -n 40 ~/infoscreen/surface/.env/schedule.json
curl -s http://127.0.0.1:8765/schedule.json | python3 -m json.tool | head -n 40
```

## Check the macOS job

```bash
launchctl print "gui/$(id -u)/com.renchili.infoscreen.schedule-sync"
tail -n 80 "$HOME/Library/Logs/infoscreen-sync/push_schedule.log"
tail -n 80 "$HOME/Library/Logs/infoscreen-sync/launchd.err.log"
```

## Check the Surface runtime

```bash
ssh <ssh-user>@<ssh-host> 'stat ~/infoscreen/surface/.env/schedule.json; head -n 20 ~/infoscreen/surface/.env/schedule.json'
```

## Reconfigure

Run the setup command again with new arguments. It safely replaces the user LaunchAgent before loading the new one.

If an older `mac/local.env` points to `~/infoscreen/schedule.json`, run setup again or edit it to:

```text
REMOTE_SCHEDULE_JSON=~/infoscreen/surface/.env/schedule.json
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
