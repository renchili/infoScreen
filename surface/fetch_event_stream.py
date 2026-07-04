#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SURFACE_DIR = Path(__file__).resolve().parent
ENV_DIR = SURFACE_DIR / ".env"
OUT = ENV_DIR / "event_stream.json"
ITEM_COUNT = 8


def google_news_rss(query: str, hl: str, gl: str, ceid: str) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})


FEEDS = [
    {"lang": "en", "source": "SG-EN", "url": google_news_rss("Singapore news", "en-SG", "SG", "SG:en"), "take": 40},
    {"lang": "en", "source": "CNA", "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "take": 40},
    {"lang": "fr", "source": "SG-FR", "url": google_news_rss("Singapour actualité", "fr", "FR", "FR:fr"), "take": 40},
    {"lang": "fr", "source": "France24", "url": "https://www.france24.com/fr/rss", "take": 40},
    {"lang": "fr", "source": "RFI", "url": "https://www.rfi.fr/fr/rss", "take": 40},
    {"lang": "zh", "source": "新加坡", "url": google_news_rss("新加坡 新闻", "zh-CN", "SG", "SG:zh-Hans"), "take": 40},
    {"lang": "zh", "source": "联合早报/8视界", "url": google_news_rss("新加坡 联合早报 8视界", "zh-CN", "SG", "SG:zh-Hans"), "take": 40},
    {"lang": "zh", "source": "BBC中文", "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "take": 40},
]


def fetch(url: str, timeout: int = 18) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Surface-Info-TTY/1.0", "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", value).strip()


def has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def mostly_latin(value: str) -> bool:
    return len(re.findall(r"[A-Za-zÀ-ÿ]", value or "")) >= 6


def text_of(node, names):
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return clean_text(child.text)
    return ""


def parse_feed(feed, raw: bytes):
    root = ET.fromstring(raw)
    items = []
    for item in root.findall(".//item"):
        title = text_of(item, ["title"])
        link = text_of(item, ["link"])
        published = text_of(item, ["pubDate", "date"])
        if title:
            items.append({"base_lang": feed["lang"], "base_source": feed["source"], "base_title": title, "link": link, "published": published or ""})

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = text_of(entry, ["{http://www.w3.org/2005/Atom}title"])
        link_node = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        published = text_of(entry, ["{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"])
        if title:
            items.append({"base_lang": feed["lang"], "base_source": feed["source"], "base_title": title, "link": link, "published": published or ""})
    return items[: feed.get("take", 40)]


def dedupe_exact(items):
    seen = set()
    out = []
    for item in items:
        key = item["base_title"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def translate_google(text: str, target_lang: str) -> str:
    tl = {"en": "en", "fr": "fr", "zh": "zh-CN"}[target_lang]
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text})
    raw = fetch(url, timeout=10)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    return clean_text("".join(item[0] for item in data[0] if item and item[0]))


def translate_strict(text: str, target_lang: str) -> str:
    last_error = None
    for _ in range(3):
        try:
            translated = translate_google(text, target_lang)
            if not translated:
                raise RuntimeError("empty translation")
            if target_lang == "zh" and not has_cjk(translated):
                raise RuntimeError("zh translation has no CJK")
            if target_lang in ("en", "fr") and not mostly_latin(translated):
                raise RuntimeError(f"{target_lang} translation has too little latin text")
            return translated
        except Exception as exc:
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError(str(last_error))


def make_item(base, target_lang: str):
    original = base["base_title"]
    title = translate_strict(original, target_lang)
    return {
        "lang": target_lang,
        "source": base["base_source"] if target_lang == base["base_lang"] else f"TR-{base['base_source']}",
        "title": title,
        "link": base.get("link", ""),
        "published": base.get("published", ""),
        "translated": target_lang != base["base_lang"],
        "translated_from": base["base_lang"] if target_lang != base["base_lang"] else "",
        "original_title": original if target_lang != base["base_lang"] else "",
        "base_source": base["base_source"],
        "base_lang": base["base_lang"],
    }


def main() -> None:
    ENV_DIR.mkdir(exist_ok=True)
    pool = []
    errors = []
    for feed in FEEDS:
        try:
            pool.extend(parse_feed(feed, fetch(feed["url"])))
        except Exception as exc:
            errors.append({"source": feed["source"], "lang": feed["lang"], "error": str(exc)[:180]})

    pool = dedupe_exact(pool)
    random.shuffle(pool)
    by_lang = {"en": [], "fr": [], "zh": []}
    base_items = []

    for base in pool:
        if len(base_items) >= ITEM_COUNT:
            break
        try:
            en = make_item(base, "en")
            fr = make_item(base, "fr")
            zh = make_item(base, "zh")
        except Exception as exc:
            errors.append({"source": base.get("base_source", ""), "lang": base.get("base_lang", ""), "title": base.get("base_title", "")[:120], "error": str(exc)[:180]})
            continue
        base_items.append(base)
        by_lang["en"].append(en)
        by_lang["fr"].append(fr)
        by_lang["zh"].append(zh)

    payload = {
        "source": "rss_random_same_items_strict_translated_3lang",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items_by_lang": by_lang,
        "items": by_lang["en"] + by_lang["fr"] + by_lang["zh"],
        "base_items": base_items,
        "errors": errors,
        "selection": {"mode": "same random base news items, strict EN/FR/ZH translation, failed triples skipped", "item_count": ITEM_COUNT, "no_keywords": True, "no_scoring": True, "no_filtering": True, "no_time_sort": True},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
