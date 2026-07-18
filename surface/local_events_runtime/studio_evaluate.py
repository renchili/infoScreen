from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from .extract import clean, label_dates
from .studio_capture import SNAPSHOT_ID_RE, snapshot_asset_path
from .studio_dom import SnapshotDom, StudioSelectorError, matches_selector, select_nodes
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRule,
    LocalEventStudioRuleStore,
    RuleNotFoundError,
    RuleStorageError,
    canonical_listing_url,
)

GENERIC_LEAVES = {
    "",
    "activity",
    "activities",
    "calendar",
    "event",
    "events",
    "exhibition",
    "exhibitions",
    "overview",
    "programme",
    "programmes",
    "program",
    "programs",
    "view-all",
    "whatson",
    "whats-on",
}
BLOCKED_SUFFIXES = {
    ".7z",
    ".avi",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}


class StudioEvaluationError(RuntimeError):
    """Raised when a snapshot test cannot produce trustworthy evidence."""


def _source_record(path: Path, source_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleStorageError(f"invalid source configuration: {exc}") from exc
    for source in payload.get("sources") or []:
        if isinstance(source, dict) and source.get("id") == source_id:
            return dict(source)
    raise RuleStorageError(f"configured source record missing: {source_id}")


def _allowed_domain(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in domains
        )
    )


def _rewrite_public_url(url: str, source: dict[str, Any]) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    for rewrite in source.get("public_detail_url_rewrites") or []:
        if not isinstance(rewrite, dict):
            continue
        old = str(rewrite.get("from") or "").rstrip("/")
        new = str(rewrite.get("to") or "").rstrip("/")
        if old and (path == old or path.startswith(old + "/")):
            path = new + path[len(old):]
            if not path.startswith("/"):
                path = "/" + path
            break
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path or "/", parsed.query, ""))


def validate_detail_url(raw: str, listing_url: str, source: dict[str, Any]) -> tuple[str, str | None]:
    """Return a public official detail URL or a stable rejection reason."""

    if not raw:
        return "", "detail_url_missing"
    absolute = urljoin(listing_url, raw)
    parsed = urlsplit(absolute)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "", "detail_url_not_http"
    if parsed.fragment or "#structured-" in absolute or "#nhb-" in absolute:
        return "", "detail_url_is_synthetic"

    rewritten = _rewrite_public_url(absolute, source)
    if not _allowed_domain(rewritten, [str(item) for item in source.get("allowed_domains") or []]):
        return "", "detail_url_outside_allowed_domain"

    parsed = urlsplit(rewritten)
    lower_path = parsed.path.lower().rstrip("/")
    if any(lower_path.endswith(suffix) for suffix in BLOCKED_SUFFIXES):
        return "", "detail_url_is_media_or_document"
    if lower_path.startswith("/api") or "/api/" in lower_path or "/content/" in lower_path:
        return "", "detail_url_is_internal_endpoint"

    listing = urlsplit(canonical_listing_url(listing_url))
    if (
        parsed.scheme.lower() == listing.scheme.lower()
        and parsed.netloc.lower() == listing.netloc.lower()
        and parsed.path.rstrip("/") == listing.path.rstrip("/")
    ):
        return "", "detail_url_is_listing"

    leaf = lower_path.rsplit("/", 1)[-1].removesuffix(".html")
    if leaf in GENERIC_LEAVES:
        return "", "detail_url_is_generic_listing"
    return rewritten, None


def _field_value(node: dict[str, Any], attribute: str | None) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    if attribute == "href":
        return clean(node.get("href") or attributes.get("href") or "")
    if attribute == "src":
        return clean(node.get("src") or attributes.get("src") or "")
    if attribute:
        return clean(attributes.get(attribute) or "")
    return clean(node.get("text") or "")


def _extract_field(
    dom: SnapshotDom,
    card: dict[str, Any],
    name: str,
    rule: Any,
) -> tuple[str, dict[str, Any] | None, str | None]:
    if rule is None:
        return "", None, f"{name}_selector_missing"
    nodes = select_nodes(dom, rule.selector, within_id=str(card.get("id") or ""))
    if not nodes:
        return ("", None, None) if rule.optional else ("", None, f"{name}_not_found")
    node = nodes[0]
    raw_value = _field_value(node, rule.attribute)
    if not raw_value:
        return ("", None, None) if rule.optional else ("", None, f"{name}_empty")
    evidence = {
        "page_role": "listing",
        "selector": rule.selector,
        "element_id": node.get("id"),
        "raw_value": raw_value,
        "normalized_value": raw_value,
        "attribute": rule.attribute,
        "precedence": "listing_mapped_field",
    }
    return raw_value, evidence, None


def rule_fingerprint(rule: LocalEventStudioRule) -> str:
    """Fingerprint only extraction semantics, excluding mutable lifecycle metadata."""

    payload = rule.model_dump(
        mode="json",
        exclude={"created_at", "updated_at", "published_at", "version", "status", "based_on_version"},
        exclude_none=True,
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_rule(
    rule: LocalEventStudioRule,
    dom_payload: dict[str, Any],
    source: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate one draft against one stored listing snapshot without network access."""

    current_date = today or date.today()
    dom = SnapshotDom(dom_payload)
    fatal_errors: list[str] = []
    cards: list[dict[str, Any]] = []

    if rule.card is None:
        fatal_errors.append("card_selector_missing")
    else:
        try:
            cards = select_nodes(dom, rule.card.selector)
        except StudioSelectorError as exc:
            fatal_errors.append(f"card_selector_invalid:{exc}")
        if not cards and not fatal_errors:
            fatal_errors.append("card_selector_matched_zero_elements")

    for name in ("title", "when", "where", "url"):
        if getattr(rule.fields, name) is None:
            fatal_errors.append(f"{name}_selector_missing")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for card in cards:
        card_id = str(card.get("id") or "")
        try:
            exclusion = next(
                (
                    selector
                    for selector in (rule.card.exclude_selectors if rule.card else [])
                    if matches_selector(dom, card, selector)
                    or bool(select_nodes(dom, selector, within_id=card_id))
                ),
                None,
            )
        except StudioSelectorError as exc:
            fatal_errors.append(f"exclude_selector_invalid:{exc}")
            break

        if exclusion:
            rejected.append(
                {
                    "card_id": card_id,
                    "reason": "excluded_by_rule",
                    "exclude_selector": exclusion,
                    "card_text": clean(card.get("text") or "")[:500],
                }
            )
            continue

        values: dict[str, str] = {}
        evidence: dict[str, Any] = {}
        reasons: list[str] = []
        try:
            for name in ("title", "when", "where", "url", "summary", "image"):
                value, field_evidence, reason = _extract_field(
                    dom,
                    card,
                    name,
                    getattr(rule.fields, name),
                )
                values[name] = value
                if field_evidence:
                    evidence[name] = field_evidence
                if reason:
                    reasons.append(reason)
        except StudioSelectorError as exc:
            reasons.append(f"field_selector_invalid:{exc}")

        if not values.get("where") and rule.fields.where and rule.fields.where.allow_source_default:
            default_venue = clean(source.get("default_venue") or source.get("name") or "")
            if default_venue:
                values["where"] = default_venue
                evidence["where"] = {
                    "page_role": "source_config",
                    "selector": None,
                    "element_id": None,
                    "raw_value": default_venue,
                    "normalized_value": default_venue,
                    "attribute": None,
                    "precedence": "explicit_source_default",
                }
                reasons = [reason for reason in reasons if reason not in {"where_not_found", "where_empty"}]

        public_url, url_reason = validate_detail_url(values.get("url", ""), rule.listing_url, source)
        if url_reason:
            reasons.append(url_reason)
        else:
            values["url"] = public_url
            if "url" in evidence:
                evidence["url"]["normalized_value"] = public_url

        dates = label_dates(values.get("when", ""))
        if not dates:
            reasons.append("when_not_parseable")
        elif rule.validation.require_current_or_future_date and max(dates) < current_date:
            reasons.append("event_expired")

        if public_url and public_url in seen_urls:
            reasons.append("duplicate_detail_url")

        reasons = list(dict.fromkeys(reasons))
        if reasons:
            rejected.append(
                {
                    "card_id": card_id,
                    "reason": reasons[0],
                    "reasons": reasons,
                    "card_text": clean(card.get("text") or "")[:500],
                    "values": values,
                    "evidence": evidence,
                }
            )
            continue

        seen_urls.add(public_url)
        accepted.append(
            {
                "card_id": card_id,
                "event": {
                    "title": values["title"],
                    "when": values["when"],
                    "where": values["where"],
                    "url": public_url,
                    "summary": values.get("summary", ""),
                    "image": values.get("image", ""),
                    "start_date": min(dates).isoformat(),
                    "source_id": rule.source_id,
                    "source_name": source.get("name") or rule.source_id,
                    "listing_url": rule.listing_url,
                    "candidate_policy": "studio-published-listing-v1",
                },
                "evidence": evidence,
                "detail_page_pending": bool(rule.detail_page.enabled),
            }
        )

    fatal_errors = list(dict.fromkeys(fatal_errors))
    warnings: list[str] = []
    if len(cards) > 250:
        warnings.append("card_selector_matches_more_than_250_elements")
    if rule.detail_page.enabled:
        warnings.append("detail_page_selectors_not_evaluated_in_listing_snapshot")

    return {
        "schema_version": 1,
        "rule_fingerprint": rule_fingerprint(rule),
        "source_id": rule.source_id,
        "listing_url": rule.listing_url,
        "card_selector": rule.card.selector if rule.card else None,
        "matched_card_count": len(cards),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "publishable": not fatal_errors and bool(accepted),
        "fatal_errors": fatal_errors,
        "warnings": warnings,
        "accepted": accepted,
        "rejected": rejected,
    }


def _load_snapshot(root: Path, source_id: str, snapshot_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise StudioEvaluationError("invalid snapshot_id")
    metadata_path = snapshot_asset_path(source_id, snapshot_id, "metadata.json", root=root)
    dom_path = snapshot_asset_path(source_id, snapshot_id, "dom.json", root=root)
    if metadata_path is None or dom_path is None:
        raise RuleNotFoundError("snapshot not found")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        dom = json.loads(dom_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioEvaluationError(f"invalid snapshot data: {exc}") from exc
    return metadata, dom


def _write_test_run(root: Path, result: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    tested_at = datetime.now(timezone.utc)
    run_id = tested_at.strftime("%Y%m%dT%H%M%S%fZ") + "-" + str(result["rule_fingerprint"])[:12]
    payload = {**result, "run_id": run_id, "snapshot_id": snapshot_id, "tested_at": tested_at.isoformat()}
    directory = root / "test-runs" / str(result["source_id"])
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{run_id}.json"
    temporary = directory / f".{run_id}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def test_draft(
    source_id: str,
    listing_url: str,
    snapshot_id: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
    today: date | None = None,
) -> dict[str, Any]:
    """Test the current draft against one matching stored snapshot and persist evidence."""

    studio_root = Path(root).expanduser().resolve()
    config_path = Path(source_config_path).expanduser().resolve()
    store = LocalEventStudioRuleStore(root=studio_root, source_config_path=config_path)
    safe_source, canonical_url = store._binding(source_id, listing_url)
    draft = store.load_draft(safe_source, canonical_url)
    if draft is None:
        raise RuleNotFoundError("draft not found")

    metadata, dom = _load_snapshot(studio_root, safe_source, snapshot_id)
    if metadata.get("source_id") != safe_source:
        raise StudioEvaluationError("snapshot source does not match draft")
    if canonical_listing_url(metadata.get("listing_url")) != canonical_url:
        raise StudioEvaluationError("snapshot listing does not match draft")

    result = evaluate_rule(draft, dom, _source_record(config_path, safe_source), today=today)
    return _write_test_run(studio_root, result, snapshot_id)


def latest_test_run(source_id: str, *, root: Path | str = DEFAULT_STUDIO_ROOT) -> dict[str, Any] | None:
    directory = Path(root).expanduser().resolve() / "test-runs" / source_id
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def require_publishable_test(
    rule: LocalEventStudioRule,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
) -> dict[str, Any]:
    """Block publication unless the current draft exactly matches a publishable test."""

    latest = latest_test_run(rule.source_id, root=root)
    if latest is None:
        raise StudioEvaluationError("draft has no completed snapshot test")
    if latest.get("listing_url") != rule.listing_url:
        raise StudioEvaluationError("latest test belongs to another listing")
    if latest.get("rule_fingerprint") != rule_fingerprint(rule):
        raise StudioEvaluationError("draft changed after the latest snapshot test")
    if latest.get("publishable") is not True:
        raise StudioEvaluationError("latest snapshot test is not publishable")
    return latest


__all__ = [
    "StudioEvaluationError",
    "evaluate_rule",
    "latest_test_run",
    "require_publishable_test",
    "rule_fingerprint",
    "test_draft",
    "validate_detail_url",
]
