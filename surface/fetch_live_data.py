#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
CONFIG = APP_ROOT / "market_config.json"
MARKET = APP_ROOT / "market.json"
DEFAULT_SYMBOLS = ["AAPL", "NVDA", "MSFT", "TSLA"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_symbols():
    data = read_json(CONFIG, {})
    raw = data.get("symbols", DEFAULT_SYMBOLS)
    if not isinstance(raw, list):
        raw = DEFAULT_SYMBOLS
    out = []
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out[:12] or DEFAULT_SYMBOLS


def req_headers(extra=None):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }
    if extra:
        headers.update(extra)
    return headers


def http_json(url, timeout=15, headers=None):
    req = urllib.request.Request(url, headers=req_headers(headers))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    if raw.lstrip().startswith("<"):
        raise RuntimeError("html response")
    return json.loads(raw)


def http_text(url, timeout=15, headers=None):
    req = urllib.request.Request(url, headers=req_headers(headers))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def clean_num(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "N/D", "--"}:
        return None
    text = re.sub(r"[^0-9.+-]", "", text)
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def pct_text(price, previous):
    try:
        price = float(price)
        previous = float(previous)
        if not math.isfinite(price) or not math.isfinite(previous) or previous == 0:
            return "N/A"
        return f"{((price - previous) / previous) * 100:+.2f}%"
    except Exception:
        return "N/A"


def normalize_symbol_for_url(symbol):
    return symbol.strip().upper().replace(".", "-")


def nasdaq_quote(symbol):
    sym = normalize_symbol_for_url(symbol)
    errors = []
    for asset in ("stocks", "etf"):
        url = f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(sym)}/info?assetclass={asset}"
        try:
            data = http_json(url, headers={"Origin": "https://www.nasdaq.com", "Referer": f"https://www.nasdaq.com/market-activity/{asset}/{sym.lower()}"})
            root = data.get("data") or {}
            primary = root.get("primaryData") or {}
            price = clean_num(primary.get("lastSalePrice") or primary.get("lastSale") or root.get("lastSalePrice"))
            pct_raw = primary.get("percentageChange") or root.get("percentageChange") or primary.get("percentChange")
            pct_num = clean_num(pct_raw)
            name = root.get("companyName") or root.get("symbol") or primary.get("symbol") or symbol
            if price is None:
                raise RuntimeError("no nasdaq price")
            return {"symbol": symbol, "name": name, "price": f"{price:.2f}", "percent": "N/A" if pct_num is None else f"{pct_num:+.2f}%", "session": "NSDQ", "provider": f"nasdaq-{asset}"}
        except Exception as exc:
            errors.append(f"{asset}: {exc}")
    raise RuntimeError("nasdaq failed: " + " | ".join(errors)[-400:])


def cnbc_quote(symbol):
    quoted = urllib.parse.quote(symbol.upper())
    url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol" + f"?symbols={quoted}&requestMethod=quick&exthrs=1&noform=1&partnerId=2&fund=1&output=json"
    data = http_json(url, headers={"Referer": "https://www.cnbc.com/quotes/" + quoted})
    result = data.get("FormattedQuoteResult") or {}
    quote = result.get("FormattedQuote") or []
    if isinstance(quote, dict):
        quote = [quote]
    if not quote:
        raise RuntimeError("empty cnbc quote")
    item = quote[0]
    price = clean_num(item.get("last") or item.get("last_price") or item.get("lastPrice"))
    pct = clean_num(item.get("change_pct") or item.get("changepct") or item.get("change_pct_format"))
    if price is None:
        raise RuntimeError("no cnbc price")
    return {"symbol": symbol, "name": item.get("name") or item.get("shortName") or symbol, "price": f"{price:.2f}", "percent": "N/A" if pct is None else f"{pct:+.2f}%", "session": "CNBC", "provider": "cnbc"}


def stooq_symbol(symbol):
    value = symbol.strip().lower()
    return value if "." in value else value + ".us"


def stooq_daily(symbol):
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_symbol(symbol))}&i=d"
    text = http_text(url)
    if not text.strip() or text.lstrip().startswith("<"):
        raise RuntimeError("invalid stooq response")
    rows = [row for row in csv.DictReader(text.splitlines()) if row.get("Close") and row.get("Close", "").upper() != "N/D"]
    if not rows:
        raise RuntimeError("stooq no rows")
    last = rows[-1]
    previous = rows[-2] if len(rows) >= 2 else rows[-1]
    close = clean_num(last.get("Close"))
    prev_close = clean_num(previous.get("Close"))
    if close is None:
        raise RuntimeError("stooq no price")
    return {"symbol": symbol, "name": symbol, "price": f"{close:.2f}", "percent": pct_text(close, prev_close), "session": "DLY", "provider": "stooq-daily"}


def yahoo_chart(symbol):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol) + "?range=1d&interval=5m"
    data = http_json(url)
    result = data.get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError("empty yahoo chart")
    meta = result[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [value for value in quote.get("close", []) if value is not None]
        if closes:
            price = closes[-1]
    if price is None:
        raise RuntimeError("no yahoo price")
    return {"symbol": symbol, "name": meta.get("shortName") or meta.get("symbol") or symbol, "price": f"{float(price):.2f}", "percent": pct_text(price, previous), "session": meta.get("marketState") or "YH", "provider": "yahoo-chart"}


def previous_item(symbol):
    old = read_json(MARKET, {})
    for item in old.get("items", []):
        if str(item.get("symbol", "")).upper() == symbol.upper():
            price = item.get("price")
            if price and price != "N/A":
                cached = dict(item)
                cached["session"] = "STALE"
                cached["provider"] = "stale-cache"
                return cached
    return None


def quote_one(symbol):
    errors = []
    for fn in (nasdaq_quote, cnbc_quote, stooq_daily, yahoo_chart):
        try:
            return fn(symbol)
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")
    cached = previous_item(symbol)
    if cached:
        cached["error"] = "live providers failed: " + " | ".join(errors)[-400:]
        return cached
    return {"symbol": symbol, "name": symbol, "price": "N/A", "percent": "N/A", "session": "ERR", "provider": "none", "error": " | ".join(errors)[-800:]}


def main() -> None:
    symbols = load_symbols()
    items = [quote_one(symbol) for symbol in symbols]
    ok_count = sum(1 for item in items if item.get("price") != "N/A")
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "source": "nasdaq+cnbc+stooq+yahoo", "symbols": symbols, "status": "OK" if ok_count else "ERR", "error": None if ok_count else "all quote providers failed", "items": items}
    MARKET.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"market updated status={payload['status']} ok={ok_count}/{len(symbols)} symbols={','.join(symbols)}")


if __name__ == "__main__":
    main()
