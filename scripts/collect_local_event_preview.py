#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the production Local Event Studio preview collector for one saved "
            "list page and write the complete raw preview payload to stdout."
        )
    )
    parser.add_argument(
        "listing_url",
        help="Exact list-page URL already present in Local Event Review state.",
    )
    return parser.parse_args()


def collect_payload(listing_url: str) -> tuple[dict[str, object], int]:
    """Call the same production function used by POST /preview-events."""

    from surface import serve_infoscreen as server

    try:
        state = server.preview_event_candidates(
            server.review_store(),
            listing_url,
        )
    except ValueError as exc:
        return (
            {
                "ok": False,
                "error": "event_preview_request_failed",
                "detail": str(exc),
            },
            2,
        )
    except Exception as exc:
        return (
            {
                "ok": False,
                "error": "event_preview_collection_failed",
                "detail": str(exc),
            },
            1,
        )

    return (
        {
            "ok": True,
            "preview": True,
            **state.model_dump(mode="json"),
        },
        0,
    )


def main() -> int:
    args = parse_args()
    payload, returncode = collect_payload(str(args.listing_url or "").strip())
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
