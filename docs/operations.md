# InfoScreen operations

This file is the first place to check when the running kiosk is stale or local runtime data is missing.

## Calendar schedule sync

Calendar data comes from the Mac, because macOS Calendar/EventKit is the schedule source. The Surface does not pull calendar data by itself.

Active flow:

```text
Mac LaunchAgent
  -> /bin/bash mac/sync_schedule.sh
  -> mac/export.py
  -> mac/schedule.json
  -> scp to Surface
  -> ~/infoscreen/surface/.env/schedule.json
  -> InfoScreen HTTP server exposes /schedule.json
```

The Surface runtime file is:

```text
~/infoscreen/surface/.env/schedule.json
```

Do not write runtime schedule data to the repository root:

```text
~/infoscreen/schedule.json
```

That root path is not the runtime env path and should stay absent.

### Configure or update the Surface IP

Run this on the Mac when the Surface IP changes:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip> \
  --user rody \
  --remote-path '~/infoscreen/surface/.env/schedule.json' \
  --interval 120
```

`setup-schedule-sync.sh` writes local-only config to:

```text
mac/local.env
```

and installs or refreshes this LaunchAgent:

```text
~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist
```

Neither file is committed to Git.

### Trigger one sync now

Run this on the Mac:

```bash
launchctl kickstart -k gui/$(id -u)/com.renchili.infoscreen.schedule-sync
```

Manual one-shot run:

```bash
cd ~/infoscreen
bash mac/sync_schedule.sh
```

### Check Mac logs

```bash
tail -n 100 ~/Library/Logs/infoscreen-sync/launchd.out.log
tail -n 100 ~/Library/Logs/infoscreen-sync/launchd.err.log
tail -n 100 ~/Library/Logs/infoscreen-sync/push_schedule.log
```

### Verify on the Surface

```bash
ssh rody@<surface-ip> 'ls -l ~/infoscreen/surface/.env/schedule.json'
ssh rody@<surface-ip> 'test ! -f ~/infoscreen/schedule.json && echo root-clean'
ssh rody@<surface-ip> 'curl -s http://127.0.0.1:8765/schedule.json | head'
```

If `~/infoscreen/schedule.json` exists on the Surface, it is stale root pollution from an old sync path. Move it once into the runtime env path, then remove the root file:

```bash
ssh rody@<surface-ip> '
  cd ~/infoscreen &&
  mkdir -p surface/.env &&
  if [ -f schedule.json ] && [ ! -L schedule.json ]; then
    mv schedule.json surface/.env/schedule.json
  fi &&
  test ! -f schedule.json && echo root-clean
'
```

## Runtime file locations

Runtime JSON files belong under:

```text
~/infoscreen/surface/.env/
```

Common files:

```text
surface/.env/schedule.json
surface/.env/weather.json
surface/.env/market.json
surface/.env/market_config.json
surface/.env/event_stream.json
surface/.env/local_event_search_results.json
surface/.env/photos.json
surface/.env/sync_status.json
```

## Repository-root hygiene check

Run this from the Surface or any clone:

```bash
cd ~/infoscreen
find . -maxdepth 1 -type f \( -name '*.json' -o -name '*.js' -o -name '*.css' \) -print
python3 scripts/ci/check_repo.py --suite all --scope repository
```

Expected root runtime output: empty. Root-level JSON, JavaScript, and CSS are not valid runtime locations for this project.
