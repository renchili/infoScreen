#!/usr/bin/env python3
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path.home() / "infoscreen"
WEATHER_OUT = BASE / "weather.json"
MARKET_OUT = BASE / "market.json"

LOCATION = "Singapore"

SYMBOLS = {
    "AAPL": "aapl.us",
    "NVDA": "nvda.us",
    "TSLA": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us",
}


def fetch_url(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Surface-Info-TTY/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_weather() -> None:
    url = f"https://wttr.in/{urllib.parse.quote(LOCATION)}?format=j1"
    raw = fetch_url(url)
    data = json.loads(raw.decode("utf-8", errors="replace"))

    cur = data.get("current_condition", [{}])[0]
    area = data.get("nearest_area", [{}])[0]

    city = LOCATION
    try:
        city = area.get("areaName", [{}])[0].get("value") or LOCATION
    except Exception:
        pass

    desc = ""
    try:
        desc = cur.get("weatherDesc", [{}])[0].get("value", "")
    except Exception:
        pass

    out = {
        "source": "wttr.in",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "location": city,
        "temp_c": cur.get("temp_C", "--"),
        "feels_like_c": cur.get("FeelsLikeC", "--"),
        "humidity": cur.get("humidity", "--"),
        "desc": desc or "unknown",
    }

    WEATHER_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {WEATHER_OUT}")


def fetch_market() -> None:
    symbols = ",".join(SYMBOLS.values())
    url = f"https://stooq.com/q/l/?s={symbols}&f=sd2t2l1c1p2&h&e=csv"
    raw = fetch_url(url)
    text = raw.decode("utf-8", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))

    reverse = {v.lower(): k for k, v in SYMBOLS.items()}
    items = []

    for row in rows:
        raw_symbol = (row.get("Symbol") or "").lower()
        name = reverse.get(raw_symbol, raw_symbol.upper())
        last = row.get("Close") or row.get("Last") or row.get("l1") or "N/A"
        change = row.get("Change") or "N/A"
        pct = row.get("% Change") or row.get("Change%") or row.get("p2") or "N/A"

        items.append({
            "symbol": name,
            "price": str(last),
            "change": str(change),
            "percent": str(pct),
            "date": row.get("Date") or "",
            "time": row.get("Time") or "",
        })

    out = {
        "source": "stooq",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }

    MARKET_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {MARKET_OUT}")


def main() -> None:
    errors = []

    try:
        fetch_weather()
    except Exception as e:
        errors.append(f"weather: {e}")
        WEATHER_OUT.write_text(json.dumps({
            "source": "error",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "location": LOCATION,
            "temp_c": "--",
            "feels_like_c": "--",
            "humidity": "--",
            "desc": str(e)[:120],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        fetch_market()
    except Exception as e:
        errors.append(f"market: {e}")
        MARKET_OUT.write_text(json.dumps({
            "source": "error",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "items": [{"symbol": "ERR", "price": "N/A", "change": "N/A", "percent": str(e)[:40]}],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        print("errors:", "; ".join(errors))


if __name__ == "__main__":
    main()
