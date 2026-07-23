from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import browser as _browser
from . import event_review as _review
from . import mandai_listing_authority as _mandai
from . import source_overrides as _source_overrides


LISTING_DIAGNOSTIC_JS = r"""
(args) => {
  const allowed = (args.allowedDomains || []).map(value => String(value).replace(/^www\./, "").toLowerCase());
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();

  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) !== 0 && rect.width >= 8 && rect.height >= 8;
  };

  const sameDomain = raw => {
    try {
      const host = new URL(raw, location.href).hostname.replace(/^www\./, "").toLowerCase();
      return allowed.some(domain => host === domain || host.endsWith("." + domain));
    } catch {
      return false;
    }
  };

  const pathRole = raw => {
    let url;
    try { url = new URL(raw, location.href); } catch { return "other"; }
    const path = decodeURIComponent(url.pathname.toLowerCase()).replace(/\/$/, "");
    const parts = path.split("/").filter(Boolean);
    const leaf = (parts[parts.length - 1] || "").replace(/\.html$/, "");
    const generic = new Set(["", "whats-on", "whatson", "overview", "view-all", "events", "event", "exhibition", "exhibitions", "programme", "programmes", "program", "programs", "activities", "activity", "guided-tours"]);
    if (/[?&](category|filter|time|date|type|page)=/i.test(url.search)) return "listing";
    if (generic.has(leaf)) return "listing";
    if (/\/(whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|guided-tours|discover-mandai\/events)\//i.test(path + "/")) return "detail";
    return "other";
  };

  const anchors = [...document.querySelectorAll("a[href]")].filter(visible);
  const sameDomainAnchors = anchors.filter(anchor => sameDomain(anchor.getAttribute("href") || ""));
  const detailAnchors = sameDomainAnchors.filter(anchor => pathRole(anchor.getAttribute("href") || "") === "detail");
  const marked = [...document.querySelectorAll("[data-infoscreen-card-id]")];

  return {
    final_url: location.href,
    page_title: clean(document.title),
    body_text_length: clean(document.body?.innerText || document.body?.textContent || "").length,
    visible_link_count: anchors.length,
    same_domain_link_count: sameDomainAnchors.length,
    detail_link_count: detailAnchors.length,
    marked_card_count: marked.length,
    detail_link_examples: detailAnchors.slice(0, 5).map(anchor => ({
      text: clean(anchor.innerText || anchor.textContent || anchor.getAttribute("aria-label") || "").slice(0, 160),
      url: new URL(anchor.getAttribute("href"), location.href).href,
    })),
  };
}
"""


RecognitionStatus = Literal["collected", "empty", "failed"]


class ListingRecognitionDiagnostic(BaseModel):
    """Explain every stage between loading a list page and producing candidates."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_name: str
    listing_url: str
    status: RecognitionStatus = "empty"
    reason_code: str = "not_started"
    reason: str = "Collection has not started."
    final_url: str = ""
    page_title: str = ""
    http_status: int | None = None
    body_text_length: int = Field(default=0, ge=0)
    visible_link_count: int = Field(default=0, ge=0)
    same_domain_link_count: int = Field(default=0, ge=0)
    detail_link_count: int = Field(default=0, ge=0)
    extracted_card_count: int = Field(default=0, ge=0)
    admitted_card_count: int = Field(default=0, ge=0)
    marked_card_count: int = Field(default=0, ge=0)
    cards_with_evidence: int = Field(default=0, ge=0)
    cards_with_selector: int = Field(default=0, ge=0)
    candidates_created: int = Field(default=0, ge=0)
    detail_collected: int = Field(default=0, ge=0)
    detail_incomplete: int = Field(default=0, ge=0)
    detail_failed: int = Field(default=0, ge=0)
    detail_link_examples: list[dict[str, str]] = Field(default_factory=list)
    error: str = ""


def _reason(diagnostic: ListingRecognitionDiagnostic) -> tuple[RecognitionStatus, str, str]:
    if diagnostic.error:
        return "failed", "page_or_collection_failed", diagnostic.error
    if diagnostic.http_status is not None and diagnostic.http_status >= 400:
        return (
            "failed",
            "listing_http_error",
            f"The listing page returned HTTP {diagnostic.http_status}.",
        )
    if diagnostic.body_text_length < 20:
        return (
            "empty",
            "listing_document_empty",
            "The page loaded, but the rendered document contained almost no visible text.",
        )
    if diagnostic.visible_link_count == 0 and diagnostic.extracted_card_count == 0:
        return (
            "empty",
            "no_visible_links_or_cards",
            "The rendered page contained no visible links or complete activity cards.",
        )
    if diagnostic.candidates_created > 0 and diagnostic.detail_link_count == 0:
        return (
            "collected",
            "events_recognised_from_complete_listing_cards",
            f"Recognised {diagnostic.candidates_created} Event candidate(s) directly "
            "from complete official listing cards without detail pages.",
        )
    if diagnostic.same_domain_link_count == 0 and diagnostic.extracted_card_count == 0:
        return (
            "empty",
            "no_same_domain_links_or_cards",
            "No allowed official link or complete activity card was recognised.",
        )
    if diagnostic.detail_link_count == 0 and diagnostic.extracted_card_count == 0:
        return (
            "empty",
            "no_detail_links_or_complete_cards",
            "No Event detail route or complete standalone activity card was recognised.",
        )
    if diagnostic.extracted_card_count == 0:
        return (
            "empty",
            "activity_links_not_isolated_into_cards",
            f"{diagnostic.detail_link_count} possible Event detail link(s) were found, "
            "but the extractor could not isolate independent activity cards.",
        )
    if diagnostic.admitted_card_count == 0:
        return (
            "empty",
            "extracted_cards_not_admitted",
            f"{diagnostic.extracted_card_count} DOM card(s) were extracted, but none "
            "contained either a usable official detail link or complete listing-card fields.",
        )
    if diagnostic.cards_with_evidence == 0:
        return (
            "empty",
            "card_dom_evidence_missing",
            f"{diagnostic.admitted_card_count} Event card(s) were admitted, but none "
            "could be matched back to a rendered DOM element for selector evidence.",
        )
    if diagnostic.cards_with_selector == 0:
        return (
            "empty",
            "card_selector_missing",
            f"{diagnostic.cards_with_evidence} card(s) had DOM evidence, but no stable "
            "selector could be generated.",
        )
    if diagnostic.candidates_created == 0:
        return (
            "empty",
            "all_recognised_cards_deduplicated",
            "Cards and selectors were recognised, but every resulting card identity "
            "duplicated a candidate already collected in this run.",
        )
    if diagnostic.detail_collected == 0 and diagnostic.detail_failed > 0:
        return (
            "collected",
            "candidates_created_detail_pages_failed",
            f"{diagnostic.candidates_created} Event candidate(s) were recognised, but "
            "every required detail-page read failed.",
        )
    if diagnostic.detail_collected == 0 and diagnostic.detail_incomplete > 0:
        return (
            "collected",
            "candidates_created_fields_incomplete",
            f"{diagnostic.candidates_created} Event candidate(s) were recognised, but "
            "their available official content did not provide all required fields.",
        )
    return (
        "collected",
        "events_recognised",
        f"Recognised {diagnostic.candidates_created} Event candidate(s) from this listing page.",
    )


def _finish(diagnostic: ListingRecognitionDiagnostic) -> ListingRecognitionDiagnostic:
    diagnostic.status, diagnostic.reason_code, diagnostic.reason = _reason(diagnostic)
    return diagnostic


def _candidate_identity(card: dict[str, Any], detail_url: str) -> str:
    if card.get("listing_only") is True:
        return str(
            card.get("listing_card_id")
            or card.get("id")
            or _mandai.card_identity(card)
        )
    return detail_url


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    """Collect confirmed pages and persist stage-by-stage recognition diagnostics."""

    state = store.load()
    confirmed = [item for item in state.listing_pages if item.decision == "confirmed"]
    if not confirmed:
        raise ValueError("no confirmed listing pages")

    sources = {str(source.get("id")): source for source in store.inventory()}
    started = _review.utc_now()
    candidates: dict[str, _review.EventCandidate] = {}
    errors: list[dict[str, str]] = []
    diagnostics: list[ListingRecognitionDiagnostic] = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                device_scale_factor=1,
            )
            page = context.new_page()
            for listing in confirmed:
                diagnostic = ListingRecognitionDiagnostic(
                    source_id=listing.source_id,
                    source_name=listing.source_name,
                    listing_url=listing.url,
                )
                source = sources.get(listing.source_id)
                if source is None:
                    diagnostic.error = "The institution is missing from event_sources.json."
                    errors.append({"listing_url": listing.url, "error": "source_not_found"})
                    diagnostics.append(_finish(diagnostic))
                    continue

                try:
                    response = None
                    try:
                        response = page.goto(
                            listing.url,
                            wait_until="networkidle",
                            timeout=_browser.NAV_TIMEOUT_MS,
                        )
                    except Exception:
                        response = page.goto(
                            listing.url,
                            wait_until="domcontentloaded",
                            timeout=_browser.DOM_TIMEOUT_MS,
                        )
                    if response is not None:
                        diagnostic.http_status = int(response.status)

                    for page_index in range(max(1, _browser.MAX_LISTING_PAGES)):
                        page.evaluate(
                            _browser.PREPARE_PAGE_JS,
                            {"maxRounds": max(0, _browser.LOAD_MORE_ROUNDS)},
                        )
                        page_url = str(page.url)
                        cards = page.evaluate(
                            _browser.CARD_JS,
                            {
                                "allowedDomains": source.get("allowed_domains") or [],
                                "maxCards": 120,
                                "sourceId": listing.source_id,
                                "pageIndex": page_index,
                                "adapter": source.get("adapter") or "rendered_dom_card",
                                "officialHome": source.get("official_home") or "",
                            },
                        ) or []
                        evidence_by_id = page.evaluate(_review.CARD_EVIDENCE_JS) or {}
                        observed = page.evaluate(
                            LISTING_DIAGNOSTIC_JS,
                            {"allowedDomains": source.get("allowed_domains") or []},
                        ) or {}

                        diagnostic.final_url = str(observed.get("final_url") or page_url)
                        diagnostic.page_title = str(observed.get("page_title") or "")
                        diagnostic.body_text_length = max(
                            diagnostic.body_text_length,
                            int(observed.get("body_text_length") or 0),
                        )
                        diagnostic.visible_link_count = max(
                            diagnostic.visible_link_count,
                            int(observed.get("visible_link_count") or 0),
                        )
                        diagnostic.same_domain_link_count = max(
                            diagnostic.same_domain_link_count,
                            int(observed.get("same_domain_link_count") or 0),
                        )
                        diagnostic.detail_link_count = max(
                            diagnostic.detail_link_count,
                            int(observed.get("detail_link_count") or 0),
                        )
                        diagnostic.marked_card_count += int(
                            observed.get("marked_card_count") or 0
                        )
                        if not diagnostic.detail_link_examples:
                            diagnostic.detail_link_examples = [
                                {
                                    "text": str(item.get("text") or "")[:160],
                                    "url": str(item.get("url") or "")[:2000],
                                }
                                for item in observed.get("detail_link_examples") or []
                                if isinstance(item, dict)
                            ][:5]

                        diagnostic.extracted_card_count += len(cards)
                        for raw_card in cards:
                            if not isinstance(raw_card, dict):
                                continue
                            card = _source_overrides._listing_card(
                                source,
                                raw_card,
                                listing.url,
                            )
                            if card is None:
                                continue
                            diagnostic.admitted_card_count += 1

                            raw_url = str(card.get("url") or "").strip()
                            evidence_raw = evidence_by_id.get(str(card.get("id") or ""))
                            if isinstance(evidence_raw, dict):
                                diagnostic.cards_with_evidence += 1
                            if not raw_url.startswith(("http://", "https://")):
                                continue
                            if not isinstance(evidence_raw, dict):
                                continue
                            if not str(evidence_raw.get("selector") or "").strip():
                                continue
                            diagnostic.cards_with_selector += 1

                            try:
                                if (
                                    card.get("listing_only") is True
                                    and _mandai.is_mandai(source)
                                ):
                                    detail = _mandai.review_detail(
                                        source,
                                        listing.url,
                                        card,
                                    )
                                else:
                                    detail = _review._detail_candidate(
                                        context,
                                        source,
                                        listing.url,
                                        raw_url,
                                        card,
                                    )
                            except Exception as exc:
                                detail = {
                                    "detail_url": raw_url,
                                    "title": _review._listing_title(card),
                                    "when": "",
                                    "where": "",
                                    "summary": "",
                                    "detail_status": "failed",
                                    "detail_error": f"{type(exc).__name__}: {exc}"[:500],
                                    "detail_page_title": "",
                                }

                            detail_status = str(
                                detail.get("detail_status") or "failed"
                            )
                            if detail_status == "collected":
                                diagnostic.detail_collected += 1
                            elif detail_status == "incomplete":
                                diagnostic.detail_incomplete += 1
                            else:
                                diagnostic.detail_failed += 1

                            final_detail_url = str(
                                detail.get("detail_url") or raw_url
                            )
                            candidate_id = _review.stable_id(
                                listing.source_id,
                                listing.url,
                                _candidate_identity(card, final_detail_url),
                            )
                            if candidate_id in candidates:
                                continue
                            candidates[candidate_id] = _review.EventCandidate(
                                candidate_id=candidate_id,
                                source_id=listing.source_id,
                                source_name=listing.source_name,
                                listing_url=listing.url,
                                detail_url=final_detail_url,
                                title=str(
                                    detail.get("title")
                                    or _review._listing_title(card)
                                ),
                                when=str(detail.get("when") or ""),
                                where=str(detail.get("where") or ""),
                                summary=str(detail.get("summary") or ""),
                                detail_status=detail_status,
                                detail_error=str(detail.get("detail_error") or ""),
                                detail_page_title=str(
                                    detail.get("detail_page_title") or ""
                                ),
                                evidence=_review._event_evidence(
                                    card,
                                    evidence_raw,
                                    page_index,
                                    page_url,
                                ),
                                collected_at=started,
                            )
                            diagnostic.candidates_created += 1

                        if page_index >= _browser.MAX_LISTING_PAGES - 1:
                            break
                        next_result = page.evaluate(
                            _browser.CLICK_NEXT_PAGE_JS,
                            {
                                "allowedDomains": source.get("allowed_domains") or [],
                                "pageIndex": page_index,
                            },
                        )
                        if not next_result.get("clicked"):
                            break
                        try:
                            page.wait_for_load_state(
                                "networkidle",
                                timeout=_browser.NEXT_WAIT_MS,
                            )
                        except Exception:
                            page.wait_for_timeout(_browser.NEXT_WAIT_MS)
                except Exception as exc:
                    diagnostic.error = f"{type(exc).__name__}: {exc}"[:500]
                    errors.append(
                        {
                            "listing_url": listing.url,
                            "error": diagnostic.error,
                        }
                    )
                diagnostics.append(_finish(diagnostic))
            context.close()
        finally:
            browser.close()

    return store.replace_events(
        list(candidates.values()),
        {
            "started_at": started,
            "completed_at": _review.utc_now(),
            "confirmed_listing_count": len(confirmed),
            "candidate_count": len(candidates),
            "errors": errors,
            "listing_diagnostics": [
                diagnostic.model_dump(mode="json") for diagnostic in diagnostics
            ],
        },
    )


def apply() -> None:
    """Install the diagnostic collector before the HTTP server imports it."""

    _review.collect_event_candidates = collect_event_candidates


__all__ = [
    "ListingRecognitionDiagnostic",
    "LISTING_DIAGNOSTIC_JS",
    "collect_event_candidates",
    "apply",
]
