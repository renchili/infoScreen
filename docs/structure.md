# InfoScreen Repository Layout

Runtime Python entrypoints are grouped under `surface/`.

```text
surface/serve_infoscreen.py
surface/fetch_live_data.py
surface/fetch_event_stream.py
surface/search_local_events.py
surface/build_photos_json.py
```

Other directories:

```text
mac/                  macOS calendar export and sync
deploy/systemd/user/  user service templates
deploy/scripts/       install helpers
scripts/ci/           repository checks
docs/                 project notes
skills/               workflow instructions
```

Generated files remain local to the deployed machine:

```text
schedule.json
market.json
market_config.json
weather.json
event_stream.json
local_event_search_results.json
photos.json
photos/
public_photos/
logs/
```

Validation commands:

```bash
python3 -m py_compile surface/*.py mac/*.py scripts/ci/*.py
python3 surface/search_local_events.py --self-test
python3 scripts/ci/check_repo.py --suite all --scope changed --base main
```
