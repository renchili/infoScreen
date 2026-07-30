#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PREVIEW_URL = "http://127.0.0.1:8765/api/local-events/review/preview-events"
PREVIEW_TIMEOUT_SECONDS = 7_600


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call the running InfoScreen HTTP service's production Local Event Studio "
            "preview route and write its complete raw response body to stdout."
        )
    )
    parser.add_argument(
        "listing_url",
        help="Exact list-page URL already present in Local Event Review state.",
    )
    return parser.parse_args()


def preview_request(listing_url: str) -> Request:
    body = json.dumps(
        {"listing_url": str(listing_url or "").strip()},
        ensure_ascii=False,
    ).encode("utf-8")
    return Request(
        PREVIEW_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def fetch_raw_response(listing_url: str) -> tuple[bytes, int]:
    """Return the exact response body and status from the running production service."""

    request = preview_request(listing_url)
    try:
        with urlopen(request, timeout=PREVIEW_TIMEOUT_SECONDS) as response:
            return response.read(), int(response.status)
    except HTTPError as exc:
        return exc.read(), int(exc.code)
    except URLError as exc:
        payload = {
            "ok": False,
            "error": "preview_service_unreachable",
            "detail": str(exc.reason),
            "service_url": PREVIEW_URL,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), 0


def main() -> int:
    args = parse_args()
    raw_body, status = fetch_raw_response(args.listing_url)
    sys.stdout.buffer.write(raw_body)
    if raw_body and not raw_body.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
