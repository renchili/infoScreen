#!/usr/bin/env python3
import json
import sys
from datetime import datetime, time, timedelta

from EventKit import EKEventStore, EKEntityTypeEvent, NSPredicate
from Foundation import NSDate


def nsdate_from_datetime(dt: datetime):
    return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "schedule.json"

    store = EKEventStore.alloc().init()

    granted = {"ok": False}

    def callback(access, error):
        granted["ok"] = bool(access)

    store.requestAccessToEntityType_completion_(EKEntityTypeEvent, callback)

    # 简单等授权回调
    import time as pytime
    for _ in range(50):
        if granted["ok"]:
            break
        pytime.sleep(0.1)

    if not granted["ok"]:
        print("Calendar access not granted", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    start = datetime.combine(now.date(), time.min)
    end = start + timedelta(days=1)

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        nsdate_from_datetime(start),
        nsdate_from_datetime(end),
        None,
    )

    events = list(store.eventsMatchingPredicate_(predicate))

    rows = []
    for e in sorted(events, key=lambda x: x.startDate().timeIntervalSince1970()):
        title = str(e.title() or "").strip()
        if not title:
            continue

        ts = e.startDate().timeIntervalSince1970()
        dt = datetime.fromtimestamp(ts)

        rows.append({
            "time": dt.strftime("%H:%M"),
            "text": title,
        })

    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
