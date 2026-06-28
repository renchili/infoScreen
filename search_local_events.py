#!/usr/bin/env python3
"""Run the local event crawler without pre-discarding fetched official pages.

The important rule here is ordering: once an official same-domain page is
fetched, parse its fields first. Do not throw the page away because a link label
or a short preview looked old/generic. Only after date extraction can the event
be treated as expired.
"""

import re
import urllib.parse

import search_local_events_v21 as crawler


def _no_old_signal(url, text):
    return False


def _score_after_fetch_first(source, url, label, context):
    if not crawler.same(url, source["domains"]) or crawler.static(url):
        return -999

    parsed = crawler.urlparse(url)
    route = urllib.parse.unquote((parsed.path + " " + parsed.query).replace("-", " ").replace("_", " ")).lower()
    text = crawler.clean(str(label or "") + " " + str(context or "")[:1800]).lower()

    score = 0
    if crawler.detail(url):
        score += 80
    if crawler.listing(url):
        score += 45
    if crawler.EVENT_RE.search(route):
        score += 20
    if crawler.EVENT_RE.search(text):
        score += 20
    if crawler.DATE_RE.search(text):
        score += 25
    if crawler.CURRENT_RE.search(text) or crawler.CURRENT_RE.search(route):
        score += 25
    if any(term in text or term in route for term in crawler.LOCAL_TERMS):
        score += 8
    return score


def _make_event_after_field_parse(source, url, title, sessions, page, obj=None, structured=False):
    title = crawler.clean(title)
    if not title or not sessions:
        return None

    dates = []
    for session in sessions:
        dates.extend(session.get("dates") or [])
    if not dates:
        return None

    # Expiry is a field-level conclusion. It is checked only after date parsing.
    if max(dates) < crawler.TODAY - crawler.timedelta(days=crawler.PAST_GRACE):
        return None

    if crawler.generic_title(title, url):
        return None

    if not structured:
        # Still require a real detail page, but do not reject because a preview
        # label said previous/past or because the first text window missed a word.
        if not crawler.detail(url):
            return None

    return {
        "title": crawler.short(title, 140),
        "when": crawler.when(sessions),
        "where": crawler.location(source, page, obj),
        "host": source["name"],
        "source_name": source["name"],
        "url": url,
        "summary": crawler.summary(page),
        "start_date": crawler.best_date(sessions).isoformat(),
        "kind": "event",
        "source_type": "official_registry",
        "structured": bool(structured),
    }


def _analyze_after_field_parse(source, url, page, label=""):
    events = []

    for obj in crawler.json_objs(page):
        for node in crawler.walk(obj):
            if crawler.is_event_obj(node):
                title = crawler.clean(node.get("name") or node.get("headline") or "")
                date_text = " - ".join(
                    str(node.get(k) or "")
                    for k in ("startDate", "endDate", "doorTime", "datePublished", "description")
                )
                sessions = crawler.sessions_from_text(date_text, 4)
                event = _make_event_after_field_parse(source, url, title, sessions, page, node, True)
                if event:
                    events.append(event)

    if events:
        return events

    title = crawler.title_of(page, label)
    # Important: include label as an auxiliary date/title source, but do not use
    # it to pre-reject the page. The fetched page remains the source of truth.
    sessions = crawler.sessions_from_text(page + " " + str(label or ""), 16)
    event = _make_event_after_field_parse(source, url, title, sessions, page, None, False)
    return [event] if event else []


crawler.old_signal = _no_old_signal
crawler.score = _score_after_fetch_first
crawler.make_event = _make_event_after_field_parse
crawler.analyze = _analyze_after_field_parse
crawler.main()
