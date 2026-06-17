#!/usr/bin/env python3
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path.home() / "infoscreen"
WEATHER_OUT = BASE / "weather.json"
MARKET_OUT = BASE / "market.json"

LOCATION = "Singapore"

DEFAULT_SYMBOLS = ["AAPL", "NVDA", "TSLA", "SPY", "QQQ"]


def load_symbols():
    if not MARKET_CONFIG.exists():
        return DEFAULT_SYMBOLS

    try:
        data = json.loads(MARKET_CONFIG.read_text())
        symbols = data.get("symbols", [])
        clean = []
        for item in symbols:
            symbol = str(item).upper().strip()
            if symbol and symbol not in clean:
                clean.append(symbol)
        return clean[:20] or DEFAULT_SYMBOLS
    except Exception:
        return DEFAULT_SYMBOLS

def fetch_url(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Surface-Info-TTY/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def fetch_weather():
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

    WEATHER_OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"wrote {WEATHER_OUT}")

def last_number(values):
    if not values:
        return None
    for v in reversed(values):
        if isinstance(v, (int, float)):
            return float(v)
    return None

def detect_session(meta: dict) -> str:
    state = meta.get("marketState") or ""
    state = str(state).upper()

    if state == "PRE":
        return "PRE"
    if state == "POST":
        return "POST"
    if state == "REGULAR":
        return "REG"
    if state == "CLOSED":
        return "CLOSED"

    return state or ""

def fetch_one_quote(symbol: str) -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}"
        "?interval=1m"
        "&range=1d"
        "&includePrePost=true"
    )

    raw = fetch_url(url)
    data = json.loads(raw.decode("utf-8", errors="replace"))

    result = data.get("chart", {}).get("result", [])
    if not result:
        err = data.get("chart", {}).get("error")
        raise RuntimeError(f"Yahoo returned no result: {err}")

    r = result[0]
    meta = r.get("meta", {})
    quote = r.get("indicators", {}).get("quote", [{}])[0]

    closes = quote.get("close") or []
    current = meta.get("regularMarketPrice")
    previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")

    # Prefer the latest 1m close because includePrePost=true includes pre/post.
    latest = last_number(closes)
    if latest is None and isinstance(current, (int, float)):
        latest = float(current)

    if latest is None:
        return {
            "symbol": symbol,
            "price": "N/A",
            "change": "N/A",
            "percent": "N/A",
            "session": detect_session(meta),
            "time": "",
        }

    if isinstance(previous_close, (int, float)) and previous_close:
        change = latest - float(previous_close)
        percent = change / float(previous_close) * 100
        change_text = f"{change:+.2f}"
        percent_text = f"{percent:+.2f}%"
    else:
        change_text = "N/A"
        percent_text = "N/A"

    timestamps = r.get("timestamp") or []
    last_ts = timestamps[-1] if timestamps else None

    if last_ts:
        time_text = datetime.fromtimestamp(last_ts).strftime("%H:%M")
    else:
        time_text = ""

    currency = meta.get("currency") or "USD"

    return {
        "symbol": symbol,
        "price": f"{latest:.2f}",
        "change": change_text,
        "percent": percent_text,
        "session": detect_session(meta),
        "currency": currency,
        "time": time_text,
        "source": "yahoo_chart",
    }

def fetch_market():
    items = []

    for symbol in load_symbols():
        try:
            item = fetch_one_quote(symbol)
        except Exception as e:
            item = {
                "symbol": symbol,
                "price": "N/A",
                "change": "N/A",
                "percent": f"ERR:{str(e)[:24]}",
                "session": "ERR",
                "time": "",
            }

        items.append(item)

    out = {
        "source": "yahoo_chart_include_prepost",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }

    MARKET_OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"wrote {MARKET_OUT}")

def main():
    fetch_weather()
    fetch_market()

if __name__ == "__main__":
    main()
