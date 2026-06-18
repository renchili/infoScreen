#!/usr/bin/env python3
import json
import re
import sys
import html
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

import trafilatura
import dateparser.search
from bs4 import BeautifulSoup


BASE = Path(__file__).resolve().parent
OUT = BASE / "local_event_search_results.json"

SEARCH_URLS = [
    "https://html.duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
]

EVENT_WORDS = [
    "event", "events", "festival", "concert", "market", "workshop",
    "exhibition", "show", "performance", "screening", "fair", "expo",
    "community", "family", "kids", "children", "music", "art",
    "theatre", "theater", "food", "nightlife", "ticket", "tickets",
    "register", "registration", "things to do", "what's on",
    "activity", "activities", "open house", "celebration"
]

BAD_WORDS = [
    "job", "jobs", "career", "salary", "property", "real estate",
    "hotel", "flight", "weather", "privacy policy", "terms of use",
    "login", "sign in", "coupon", "promo code", "download app"
]

BAD_URL_PARTS = [
    "/search", "/tag/", "/category/", "/author/", "/privacy", "/terms",
    "/login", "/signup", "/account", "/jobs", "/careers", "/cdn-cgi/"
]

BAD_NAV_TEXT = {
    "next", "previous", "more", "images", "videos", "maps", "news",
    "feedback", "settings", "privacy", "terms"
}


def clean_text(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_html(url, timeout=18, max_bytes=1000000):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-SG,en;q=0.9",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(max_bytes)

    if ctype and any(x in ctype.lower() for x in ["image/", "application/pdf", "video/", "audio/"]):
        raise RuntimeError(f"unsupported content-type: {ctype}")

    return raw.decode("utf-8", errors="replace")


def extract_target_url(href):
    href = html.unescape(str(href or "")).strip()
    if not href:
        return ""

    href = urllib.parse.urljoin("https://duckduckgo.com/", href)
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)

    if "uddg" in qs:
        return qs["uddg"][0]

    if "u" in qs and "duckduckgo.com" in parsed.netloc:
        return qs["u"][0]

    return href


def is_external_url(url):
    if not url.startswith("http"):
        return False

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()

    if not host:
        return False

    if host in {"w3.org", "www.w3.org"}:
        return False

    if "duckduckgo.com" in host:
        return False

    if any(x in host for x in ["google.com", "bing.com", "yahoo.com"]):
        return False

    if "loose.dtd" in path or "/tr/html" in path:
        return False

    if any(x in path for x in BAD_URL_PARTS):
        return False

    if re.search(r"\.(png|jpg|jpeg|gif|svg|css|js|ico|pdf|dtd|xml)(\?|$)", url, re.I):
        return False

    return True


def build_queries(location):
    loc = str(location or "Singapore").strip()

    parts = [x for x in re.split(r"\s+", loc) if x]
    area = loc
    if len(parts) >= 2 and parts[0].lower() in {"singapore", "sg"}:
        area = " ".join(parts[1:])

    # 少量高质量 query，避免 DDG anomaly / bot block
    queries = [
        f"{area} events Singapore",
        f"{area} upcoming events Singapore",
        f"{area} community events Singapore",
        f"{area} onePA events",
        f"{area} things to do Singapore",
    ]

    out = []
    for q in queries:
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in out:
            out.append(q)

    return out



def is_ddg_blocked(body):
    low = body.lower()
    if "anomaly" in low and "bot" in low:
        return True
    if "captcha" in low:
        return True
    if "unusual traffic" in low:
        return True
    # 正常 DDG 结果页通常应该有结果链接或 uddg
    if low.count("<a ") <= 3 and "uddg=" not in low and "result__a" not in low:
        return True
    return False


def ddg_request(query, query_idx):
    bodies = []

    for source_idx, base_url in enumerate(SEARCH_URLS):
        url = base_url + "?" + urllib.parse.urlencode({
            "q": query,
            "kl": "sg-en",
        })

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-SG,en;q=0.9",
                "Referer": "https://duckduckgo.com/",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                (BASE / f"ddg_debug_q{query_idx}_{source_idx}.html").write_text(
                    body,
                    encoding="utf-8",
                    errors="ignore",
                )
                bodies.append(body)
        except Exception as exc:
            (BASE / f"ddg_debug_q{query_idx}_{source_idx}_error.txt").write_text(
                str(exc),
                encoding="utf-8",
                errors="ignore",
            )

    return bodies


def parse_ddg_results(body):
    results = []
    seen = set()
    soup = BeautifulSoup(body, "html.parser")

    def add_result(href, text):
        text = clean_text(text)
        if not text:
            return

        low = text.lower().strip()
        if low in BAD_NAV_TEXT or len(low) < 4:
            return

        target = extract_target_url(href)
        target = html.unescape(urllib.parse.unquote(target)).strip()

        if not is_external_url(target):
            return

        key = target.split("?")[0].rstrip("/")
        if key in seen:
            return

        seen.add(key)

        host = urllib.parse.urlparse(target).netloc.lower().replace("www.", "")

        results.append({
            "title": text[:180],
            "url": target[:1000],
            "source": host[:100],
            "summary": text[:300],
        })

    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        cls = " ".join(a.get("class") or [])
        text = a.get_text(" ", strip=True)

        if "result__a" in cls or "result-link" in cls or "uddg=" in href:
            add_result(href, text)

    if results:
        return results

    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        text = a.get_text(" ", strip=True)

        if "uddg=" not in href and not href.startswith("http") and not href.startswith("//"):
            continue

        add_result(href, text)

    return results


def ddg_search(location, max_candidates=20):
    candidates = []
    seen = set()
    queries = build_queries(location)

    for idx, query in enumerate(queries):
        bodies = ddg_request(query, idx)

        for body in bodies:
            if is_ddg_blocked(body):
                # DDG 已经返回 anomaly/bot 页面，继续打只会更糟
                return queries, candidates

            for item in parse_ddg_results(body):
                key = item["url"].split("?")[0].rstrip("/")
                if key in seen:
                    continue

                seen.add(key)
                candidates.append(item)

                if len(candidates) >= max_candidates:
                    return queries, candidates

        time.sleep(1.5)

    return queries, candidates


def extract_page_info(page, url):
    soup = BeautifulSoup(page, "html.parser")

    title = ""

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]

    if not title and soup.title and soup.title.string:
        title = soup.title.string

    desc = ""

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]

    if not desc:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc["content"]

    readable = trafilatura.extract(
        page,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=False,
    )

    text = clean_text(readable or soup.get_text(" "))

    return clean_text(title), clean_text(desc), text[:12000]


def find_dates(text):
    try:
        hits = dateparser.search.search_dates(
            text[:8000],
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
    seen = set()

    for raw, dt in hits:
        raw = clean_text(raw)
        if not raw:
            continue

        key = raw.lower()
        if key in seen:
            continue

        # 过滤明显无意义日期词
        if key in {"login", "sign up", "search", "event", "events"}:
            continue

        seen.add(key)

        out.append({
            "raw": raw,
            "iso": dt.isoformat(),
        })

        if len(out) >= 5:
            break

    return out


def is_listing_page(url, title):
    path = urllib.parse.urlparse(url).path.lower().rstrip("/")
    text = f"{path} {title.lower()}"

    markers = [
        "/events", "/calendar", "/events-calendar", "/whats-on", "/whatson",
        "/things-to-do", "/all-happenings", "/nightlife", "/concerts",
        "/exhibitions", "/markets", "/workshops"
    ]

    if re.search(r"/d/[^/]+/events/?$", path):
        return True

    return any(x in text for x in markers)


def contains_location(text, location):
    low = text.lower()
    loc = location.lower()

    parts = [x for x in re.split(r"\W+", loc) if len(x) >= 3]

    if loc in low:
        return True

    # Singapore Punggol 这种，命中 Punggol 就算本地相关
    for p in parts:
        if p not in {"singapore", "sg"} and p in low:
            return True

    return False


def infer_event_type(text):
    low = text.lower()

    if any(x in low for x in ["concert", "music", "gig"]):
        return "Live music event"
    if any(x in low for x in ["workshop", "training", "class", "learn"]):
        return "Workshop or learning activity"
    if any(x in low for x in ["exhibition", "gallery", "art"]):
        return "Exhibition or arts event"
    if any(x in low for x in ["market", "fair", "food"]):
        return "Market or food event"
    if any(x in low for x in ["family", "kids", "children"]):
        return "Family activity"
    if any(x in low for x in ["community", "resident", "neighbourhood", "neighborhood", "cc"]):
        return "Community event"
    if "festival" in low:
        return "Festival"

    return "Local event"


def infer_who(text):
    low = text.lower()

    if any(x in low for x in ["family", "kids", "children", "parent"]):
        return "Families and children"
    if any(x in low for x in ["resident", "community", "neighbourhood", "neighborhood", "cc"]):
        return "Local residents"
    if any(x in low for x in ["workshop", "training", "class"]):
        return "Learners and participants"
    if any(x in low for x in ["concert", "nightlife", "party", "music"]):
        return "Music and nightlife visitors"

    return "Local visitors"


def infer_how(text):
    low = text.lower()

    if any(x in low for x in ["buy tickets", "ticket", "tickets"]):
        return "Buy tickets online"
    if any(x in low for x in ["register", "registration", "sign up", "rsvp"]):
        return "Register online"
    if any(x in low for x in ["free", "walk-in", "walk in"]):
        return "Walk in or check details online"

    return "Open link for details"


def extract_where(text, location):
    low = text.lower()

    # 优先直接包含 Punggol / Singapore 的短句
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)

    for s in sentences:
        if contains_location(s, location) and len(s) <= 180:
            return clean_text(s)[:120]

    if "punggol" in low:
        return "Punggol, Singapore"

    if "singapore" in low:
        return "Singapore"

    return location


def build_poster(candidate, page_title, page_desc, page_text, location):
    full_text = clean_text(" ".join([
        candidate.get("title", ""),
        candidate.get("summary", ""),
        page_title,
        page_desc,
        page_text[:8000],
    ]))

    low = full_text.lower()

    listing = is_listing_page(candidate["url"], candidate.get("title") or page_title)

    event_hits = [w for w in EVENT_WORDS if w in low]
    bad_hits = [w for w in BAD_WORDS if w in low[:2500]]
    dates = find_dates(full_text)

    title = candidate.get("title") or page_title or candidate.get("source") or "Local event"

    what = infer_event_type(full_text)

    if dates:
        when = dates[0]["raw"]
    else:
        when = "Check date online"

    where = extract_where(full_text, location)
    who = infer_who(full_text)

    why = "Discover local activities nearby"
    if any(x in low for x in ["community", "resident", "neighbourhood", "neighborhood"]):
        why = "Join nearby community activities"
    elif any(x in low for x in ["concert", "music", "festival", "market", "food", "art", "exhibition"]):
        why = "Enjoy local entertainment and activities"
    elif any(x in low for x in ["workshop", "training", "class"]):
        why = "Learn or participate in a local session"

    how = infer_how(full_text)

    if listing:
        poster_title = f"{location} Local Events"
    else:
        poster_title = title

    poster_subtitle = f"{when} · {where}"
    poster_summary = f"{what} for {who.lower()}. {how}."

    score = 0
    reasons = []

    if contains_location(full_text, location):
        score += 35
        reasons.append("location_match")

    if event_hits:
        score += min(len(event_hits) * 8, 35)
        reasons.append("event_words")

    if dates:
        score += 10
        reasons.append("date_detected")

    if listing:
        score += 10
        reasons.append("listing_page")

    if bad_hits:
        score -= min(len(bad_hits) * 15, 45)
        reasons.append("bad_words")

    score = max(0, min(100, score))

    is_event = score >= 35 and bool(event_hits or listing)

    summary = page_desc or candidate.get("summary") or poster_summary

    return {
        "is_event": is_event,
        "score": score,
        "reasons": reasons,
        "listing": listing,

        "title": clean_text(title)[:120],
        "summary": clean_text(summary)[:240],

        "poster_title": clean_text(poster_title)[:80],
        "poster_subtitle": clean_text(poster_subtitle)[:120],
        "poster_summary": clean_text(poster_summary)[:180],

        "what": clean_text(what)[:120],
        "when": clean_text(when)[:100],
        "where": clean_text(where)[:120],
        "who": clean_text(who)[:100],
        "why": clean_text(why)[:140],
        "how": clean_text(how)[:140],
    }


def verify_candidate(candidate, location):
    try:
        page = fetch_html(candidate["url"])
    except Exception as exc:
        return None, {
            "candidate": candidate,
            "reason": f"fetch_failed: {exc}",
        }

    page_title, page_desc, page_text = extract_page_info(page, candidate["url"])

    if len(page_title) + len(page_desc) + len(page_text) < 80:
        return None, {
            "candidate": candidate,
            "reason": "thin_page",
        }

    poster = build_poster(
        candidate=candidate,
        page_title=page_title,
        page_desc=page_desc,
        page_text=page_text,
        location=location,
    )

    if not poster["is_event"]:
        return None, {
            "candidate": candidate,
            "reason": "rejected",
            "score": poster["score"],
            "reasons": poster["reasons"],
            "title": poster["title"],
        }

    source = urllib.parse.urlparse(candidate["url"]).netloc.lower().replace("www.", "")

    return {
        "title": poster["title"],
        "source": source,
        "summary": poster["summary"],
        "url": candidate["url"],
        "tag": location[:60],
        "score": poster["score"],
        "verified": True,
        "verify_reason": ",".join(poster["reasons"]),
        "listing": poster["listing"],

        "poster_title": poster["poster_title"],
        "poster_subtitle": poster["poster_subtitle"],
        "poster_summary": poster["poster_summary"],

        "what": poster["what"],
        "when": poster["when"],
        "where": poster["where"],
        "who": poster["who"],
        "why": poster["why"],
        "how": poster["how"],
    }, None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    location = str(payload.get("location") or "Singapore").strip()[:100]

    try:
        limit = int(payload.get("limit", 8))
    except Exception:
        limit = 8

    limit = max(3, min(limit, 12))

    error = None
    results = []
    rejected = []

    try:
        queries, candidates = ddg_search(location, max_candidates=35)

        seen_results = set()

        for candidate in candidates[:18]:
            item, reject = verify_candidate(candidate, location)

            if item:
                key = item["url"].split("?")[0].rstrip("/")
                if key not in seen_results:
                    seen_results.add(key)
                    results.append(item)
                    results.sort(key=lambda x: x.get("score", 0), reverse=True)

            elif reject:
                rejected.append(reject)

            if len(results) >= limit:
                break

            time.sleep(0.08)

    except Exception as exc:
        queries = build_queries(location)
        candidates = []
        error = str(exc)

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "location": location,
        "extractor": "minimal: bs4 + trafilatura + dateparser",
        "queries": queries,
        "results": results[:limit],
        "candidates_checked": len(candidates),
        "debug_candidates": candidates[:10],
        "rejected_preview": rejected[:8],
        "error": error,
    }

    # 如果这次 DDG 被挡导致完全没有结果，不要用空结果覆盖旧缓存
    if not out.get("results") and OUT.exists():
        try:
            old = json.loads(OUT.read_text())
            if old.get("results"):
                out["results"] = old["results"]
                out["fallback_cache"] = True
                out["fallback_reason"] = "DDG returned anomaly/bot page or no candidates"
        except Exception:
            pass

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
