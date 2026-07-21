from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from . import output as _output

_APPLIED = False
_BASE_INVALID_EVENT = None


def _canonical(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _verified_listing_only(event: dict) -> bool:
    if event.get("listing_only") is not True:
        return False
    if str(event.get("candidate_policy") or "") != _output.VERIFIED_POLICY:
        return False
    url = _canonical(event.get("url"))
    listing_url = _canonical(event.get("listing_url"))
    if not url or url != listing_url:
        return False
    path = urlsplit(url).path.lower()
    return bool(path and not _output.MEDIA_RE.search(path))


def invalid_event(event: dict, *, allow_unverified: bool = False) -> bool:
    """Allow only verified listing-only rows to use their official list URL."""

    invalid = _BASE_INVALID_EVENT(event, allow_unverified=allow_unverified)
    return bool(invalid and not _verified_listing_only(event))


def apply() -> None:
    global _APPLIED, _BASE_INVALID_EVENT
    if _APPLIED:
        return
    _BASE_INVALID_EVENT = _output._invalid_event
    _output._invalid_event = invalid_event
    _APPLIED = True


__all__ = ["apply", "invalid_event"]
