#!/usr/bin/env python3
import json
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

import dateparser.search
import extruct
import trafilatura
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from w3lib.html import get_base_url


EVENT_KEYWORDS = [
    "event", "events", "concert", "festival", "exhibition", "market",
    "workshop", "performance", "show", "screening", "ticket", "tickets",
    "things to do", "what's on", "calendar", "venue", "register"
]


def clean_text(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def extract_schema_events(html, url):
    try:
        data = extruct.extract(
            html,
            base_url=get_base_url(html, url),
            syntaxes=["json-ld", "microdata"],
            uniform=True,
        )
    except Exception:
        return []

    found = []

    def walk(x):
        if isinstance(x, dict):
            t = x.get("@type") or x.get("type")
            if t == "Event" or (isinstance(t, list) and "Event" in t):
                found.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    return found


def schema_event_to_item(e):
    title = e.get("name") or e.get("headline") or ""
    start = e.get("startDate") or e.get("start_date") or ""
    loc = e.get("location") or ""

    if isinstance(loc, dict):
        name = loc.get("name") or ""
        addr = loc.get("address") or ""
        if isinstance(addr, dict):
            addr = " ".join(str(addr.get(k, "")) for k in [
                "streetAddress", "addressLocality", "addressRegion", "addressCountry"
            ])
        loc = f"{name} {addr}".strip()

    return {
        "title": clean_text(str(title)),
        "date": clean_text(str(start)),
        "location": clean_text(str(loc)),
    }


def extract_readable(html, url):
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )

    soup = BeautifulSoup(html, "html.parser")
    title = ""

    if soup.title and soup.title.string:
        title = soup.title.string

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]

    desc = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]

    if not desc:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc["content"]

    text = clean_text(extracted or soup.get_text(" "))
    return clean_text(title), clean_text(desc), text


def find_dates(text):
    try:
        hits = dateparser.search.search_dates(
            text[:6000],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": datetime.now(),
            },
        )
    except Exception:
        return []

    if not hits:
        return []

    out = []
    for raw, dt in hits[:5]:
        out.append({
            "raw": raw,
            "iso": dt.isoformat(),
        })
    return out


def classify_and_extract(html, url, location):
    host = urlparse(url).netloc.replace("www.", "")
    schema_events = extract_schema_events(html, url)
    title, desc, text = extract_readable(html, url)

    combined = f"{title} {desc} {text[:8000]}".lower()
    loc_score = fuzz.partial_ratio(location.lower(), combined)

    keyword_hits = [k for k in EVENT_KEYWORDS if k in combined]
    dates = find_dates(combined)

    score = 0
    reasons = []

    if schema_events:
      score += 5
      reasons.append("schema_event")

    if loc_score >= 70:
      score += 3
      reasons.append("location_match")

    if keyword_hits:
      score += min(len(keyword_hits), 5)
      reasons.append("event_keywords")

    if dates:
      score += 3
      reasons.append("date_detected")

    is_event_page = score >= 6

    # 优先具体 schema event；没有就用网页 title/description
    extracted = None
    if schema_events:
        item = schema_event_to_item(schema_events[0])
        if item["title"]:
            extracted = item

    if not extracted:
        extracted = {
            "title": title,
            "date": dates[0]["raw"] if dates else "",
            "location": location if loc_score >= 70 else "",
        }

    summary_parts = []
    if extracted.get("date"):
        summary_parts.append(extracted["date"])
    if extracted.get("location"):
        summary_parts.append(extracted["location"])
    if desc:
        summary_parts.append(desc)

    return {
        "is_event_page": is_event_page,
        "score": score,
        "reasons": reasons,
        "title": extracted.get("title") or title or host,
        "summary": " · ".join(summary_parts)[:240] or desc[:240] or text[:240],
        "source": host,
        "url": url,
        "dates": dates,
        "schema_event_count": len(schema_events),
    }


def main():
    payload = json.loads(sys.stdin.read())
    html = payload["html"]
    url = payload["url"]
    location = payload.get("location", "Singapore")
    print(json.dumps(classify_and_extract(html, url, location), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
