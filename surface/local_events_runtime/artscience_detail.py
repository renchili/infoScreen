from __future__ import annotations

from typing import Any

from . import extract as _extract
from . import listing_provenance_authority as _provenance
from . import review_detail_navigation_authority as _detail_navigation


ARTSCIENCE_DETAIL_READY_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(element => clean(element.innerText || element.textContent || ""));
  const root = document.querySelector("main") || document.querySelector("article") || document.body;
  const text = clean(root ? (root.innerText || root.textContent || "") : "");
  return Boolean(
    heading &&
    document.readyState === "complete" &&
    text.length >= 200
  );
}
"""


# ArtScience detail pages put the activity schedule in a compact "Exhibition Details",
# "Event Details", or equivalent block immediately after the activity h1. Scanning only
# that bounded area prevents dates from related activities and the global opening-hours
# footer from being attributed to the current activity.
ARTSCIENCE_DETAIL_FIELDS_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const key = value => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(element => clean(element.innerText || element.textContent || "")) || null;
  const title = clean(heading ? (heading.innerText || heading.textContent) : "");
  const root = (heading && heading.closest("main")) ||
    document.querySelector("main") ||
    (heading && heading.closest("article")) ||
    document.querySelector("article") ||
    document.body;
  const lines = String(root ? (root.innerText || root.textContent || "") : "")
    .split(/\n+/)
    .map(clean)
    .filter(Boolean);

  const titleKey = key(title);
  const titleIndex = lines.findIndex(line => {
    const lineKey = key(line);
    return Boolean(titleKey && (
      lineKey === titleKey || lineKey.includes(titleKey) || titleKey.includes(lineKey)
    ));
  });
  const detailsIndex = lines.findIndex((line, index) =>
    index > titleIndex &&
    /^(?:exhibition|event|programme|program|experience)\s+details$/i.test(line)
  );
  const start = detailsIndex >= 0 ? detailsIndex + 1 : Math.max(0, titleIndex + 1);
  const facts = lines.slice(start, start + (detailsIndex >= 0 ? 18 : 45));

  const month = "(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)";
  const fullRange = new RegExp(
    "\\b\\d{1,2}(?:st|nd|rd|th)?\\s+" + month +
    "\\s+20\\d{2}\\s*[-–—]\\s*\\d{1,2}(?:st|nd|rd|th)?\\s+" +
    month + "\\s+20\\d{2}\\b",
    "i"
  );
  const oneDate = new RegExp(
    "\\b\\d{1,2}(?:st|nd|rd|th)?\\s+" + month + "\\s+20\\d{2}\\b",
    "i"
  );
  const isoDate = /\b20\d{2}-\d{1,2}-\d{1,2}\b/;
  const when = facts.find(line =>
    line.length <= 220 && (fullRange.test(line) || oneDate.test(line) || isoDate.test(line))
  ) || "";

  let where = "";
  for (let index = 0; index < facts.length; index += 1) {
    if (!/^(?:location|venue|where)\s*:?$/i.test(facts[index])) continue;
    where = clean(facts[index + 1] || "");
    break;
  }

  const summary = clean(document.querySelector('meta[name="description"]')?.content) ||
    clean(document.querySelector('meta[property="og:description"]')?.content);
  return {
    title,
    when,
    where,
    summary,
    detail_page_title: title || clean(document.title),
    facts,
  };
}
"""


def _safe_requested_url(listing_url: str, raw_url: str) -> str:
    requested_url = _provenance.listing_detail_url(listing_url, raw_url)
    if not requested_url:
        raise ValueError("detail URL is not a safe HTTP(S) target from the listing")
    return requested_url


def read_loaded_detail_candidate(
    page: Any,
    source: dict[str, Any],
    listing_url: str,
    requested_url: str,
) -> dict[str, str]:
    """Parse an ArtScience page already opened by a rendered browser interaction."""

    requested_url = _safe_requested_url(listing_url, requested_url)
    try:
        page.wait_for_function(
            ARTSCIENCE_DETAIL_READY_JS,
            timeout=_detail_navigation.DETAIL_CONTENT_WAIT_MS,
        )
    except Exception:
        pass

    payload = page.evaluate(ARTSCIENCE_DETAIL_FIELDS_JS) or {}
    if not isinstance(payload, dict):
        payload = {}

    final_url = _provenance.listing_detail_url(
        listing_url,
        str(page.url or ""),
    ) or requested_url
    title = _extract.clean(payload.get("title") or page.title() or "")
    when = _extract.clean(payload.get("when"))
    where = _extract.clean(payload.get("where")) or _extract.clean(
        source.get("default_venue")
    )
    summary = _extract.clean(payload.get("summary"))
    detail_page_title = _extract.clean(
        payload.get("detail_page_title") or page.title() or title
    )

    missing = [
        name
        for name, value in (("title", title), ("when", when), ("where", where))
        if not value
    ]
    return {
        "detail_url": final_url,
        "title": title,
        "when": when,
        "where": where,
        "summary": summary,
        "detail_status": "incomplete" if missing else "collected",
        "detail_error": "missing_detail_" + "_and_".join(missing) if missing else "",
        "detail_page_title": detail_page_title,
    }


def collect_detail_candidate(
    page: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
) -> dict[str, str]:
    """Navigate directly for non-Preview callers, then parse the loaded page."""

    requested_url = _safe_requested_url(listing_url, raw_url)
    response = page.goto(
        requested_url,
        wait_until="commit",
        timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS,
    )
    if response is not None and response.status >= 400:
        raise ValueError(f"detail_http_status_{response.status}")
    return read_loaded_detail_candidate(page, source, listing_url, requested_url)


__all__ = [
    "ARTSCIENCE_DETAIL_FIELDS_JS",
    "ARTSCIENCE_DETAIL_READY_JS",
    "collect_detail_candidate",
    "read_loaded_detail_candidate",
]
