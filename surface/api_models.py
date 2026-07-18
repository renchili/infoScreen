from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

try:
    from .local_events_runtime.studio_rules import LocalEventStudioRule
except ImportError:
    from local_events_runtime.studio_rules import LocalEventStudioRule


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: Literal[False] = Field(False, description="Whether the request succeeded.")
    error: str = Field(..., description="Stable machine-readable error code or human-readable legacy error message.")
    detail: str | None = Field(None, description="Validation detail safe to show to the local operator.")


class RuntimeMissingResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: Literal[False] = Field(False, description="Whether the runtime JSON exists and is usable.")
    error: Literal["missing_runtime_json"] = Field("missing_runtime_json", description="Runtime JSON file is missing.")
    expected_path: str = Field(..., description="Expected runtime JSON path on local disk.")


class MarketConfigRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=12, description="Ticker symbols requested by the dashboard.")


class MarketConfigResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool | None = Field(None, description="Present on write responses.")
    symbols: list[str] = Field(..., description="Active ticker symbols.")
    updated_at: str | None = Field(None, description="UTC ISO timestamp for write responses.")


class MarketRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = Field(..., description="Whether fetch_live_data.py exited successfully.")
    returncode: int | None = Field(None, description="Subprocess return code.")
    stdout: str = Field("", description="Tail of subprocess stdout.")
    stderr: str = Field("", description="Tail of subprocess stderr.")
    market: dict[str, Any] = Field(default_factory=dict, description="Current market runtime payload.")


class LocalEventSearchRequest(BaseModel):
    location: str = Field("Punggol Singapore", description="Location query shown to the extractor and UI.")


class LocalEventRuntimeInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    writer: str | None = Field(None, description="Python writer function that produced the runtime JSON.")
    pid: int | None = Field(None, description="Writer process ID.")
    cwd: str | None = Field(None, description="Writer current working directory.")
    python: str | None = Field(None, description="Python executable used by the writer.")
    module_file: str | None = Field(None, description="Extractor module path.")
    git_head: str | None = Field(None, description="Git HEAD seen by the writer.")


class LocalEventItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(..., description="Display title of the local event.")
    when: str | None = Field(None, description="Date/time/date-range substring only; must not be the whole card text.")
    where: str | None = Field(None, description="Venue phrase or official-source fallback venue.")
    host: str | None = Field(None, description="Organizer or source display name.")
    source_name: str | None = Field(None, description="Official source display name.")
    url: HttpUrl = Field(..., description="Official HTTP/HTTPS detail URL.")
    summary: str | None = Field(None, description="Short readable display summary.")
    start_date: str | None = Field(None, description="Best parseable start date in YYYY-MM-DD form.")
    kind: Literal["event"] = Field("event", description="Item type.")
    source_type: Literal["rendered_dom_card"] | str = Field("rendered_dom_card", description="Extractor source type.")
    debug_screenshot: str | None = Field(None, description="Local debug screenshot path when available.")


class LocalEventSourceSummary(BaseModel):
    title: str | None = Field(None, description="Official source display title.")
    url: HttpUrl | str | None = Field(None, description="Official source homepage URL.")


class LocalEventSourceDebug(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str | None = Field(None, description="Official source display name.")
    adapter: str | None = Field(None, description="Extractor adapter name.")
    listing_urls: list[str] = Field(default_factory=list, description="Listing URLs fetched for this source.")
    listing_fetched: int = Field(0, description="Number of listing pages fetched.")
    cards_found: int = Field(0, description="Number of rendered DOM cards found.")
    accepted: int = Field(0, description="Number of accepted events.")
    accepted_preview: list[dict[str, Any]] = Field(default_factory=list, description="Short preview of accepted events.")
    not_output_preview: list[dict[str, Any]] = Field(default_factory=list, description="Reasons cards were not output.")
    reason_counts: dict[str, int] = Field(default_factory=dict, description="Counts by accept/reject reason.")
    screenshots: list[str] = Field(default_factory=list, description="Page or card screenshot paths.")


class LocalEventSearchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = Field(..., description="Whether the latest search/read operation succeeded.")
    version: int | None = Field(None, description="Extractor output schema version.")
    extractor: str | None = Field(None, description="Extractor implementation/version label.")
    updated_at: str | None = Field(None, description="UTC ISO timestamp.")
    location: str | None = Field(None, description="Location used for the search.")
    runtime: LocalEventRuntimeInfo | None = Field(None, description="Writer runtime metadata.")
    event_source_config: str | None = Field(None, description="Event source config file name.")
    source_count: int | None = Field(None, description="Number of configured event sources.")
    count: int = Field(0, description="Number of result items.")
    sources: list[LocalEventSourceSummary] = Field(default_factory=list, description="Configured official sources.")
    results: list[LocalEventItem] = Field(default_factory=list, description="Renderable local event items.")
    debug_by_source: list[LocalEventSourceDebug] = Field(default_factory=list, description="Extractor debug details by source.")
    stdout: str | None = Field(None, description="Tail of subprocess stdout for POST responses.")
    stderr: str | None = Field(None, description="Tail of subprocess stderr for POST responses.")


class StudioRuleBindingRequest(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=64, description="Configured Local Events source ID.")
    listing_url: str = Field(..., min_length=8, max_length=2048, description="Configured official listing URL.")


class StudioRuleRollbackRequest(StudioRuleBindingRequest):
    version: int = Field(..., ge=1, description="Historical published version to republish as a new version.")


class StudioRuleImportRequest(BaseModel):
    rule: dict[str, Any] = Field(..., description="Validated Local Event Studio rule object imported as a draft.")


class StudioRuleResponse(BaseModel):
    ok: Literal[True] = True
    rule: LocalEventStudioRule


class StudioRuleDeleteResponse(BaseModel):
    ok: Literal[True] = True
    deleted: bool = Field(..., description="Whether a draft existed and was deleted.")


class StudioRuleListResponse(BaseModel):
    ok: Literal[True] = True
    source_id: str
    listing_url: str
    draft: LocalEventStudioRule | None = None
    published: LocalEventStudioRule | None = None
    history: list[LocalEventStudioRule] = Field(default_factory=list)


class StudioSourceListingState(BaseModel):
    listing_url: str
    has_draft: bool = False
    published_version: int | None = None
    history_versions: list[int] = Field(default_factory=list)


class StudioSourceState(BaseModel):
    source_id: str
    name: str | None = None
    listing_urls: list[StudioSourceListingState] = Field(default_factory=list)


class StudioSourcesResponse(BaseModel):
    ok: Literal[True] = True
    sources: list[StudioSourceState] = Field(default_factory=list)


class PhotoItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    src: str = Field(..., description="Public photo URL.")
    name: str | None = Field(None, description="Display file name/caption.")


class PhotosResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[PhotoItem] = Field(default_factory=list, description="Photo wall items.")


class EventStreamResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[dict[str, Any]] = Field(default_factory=list, description="Flat event/news stream items.")
    items_by_lang: dict[str, list[dict[str, Any]]] | None = Field(None, description="Event/news stream grouped by language.")


class ScheduleItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    time: str | None = Field(None, description="Display time.")
    title: str | None = Field(None, description="Display title.")
    text: str | None = Field(None, description="Alternative display text.")
    start: str | None = Field(None, description="Start time/date.")
    start_time: str | None = Field(None, description="Start time/date.")
    date: str | None = Field(None, description="Display date.")


class ScheduleResponse(BaseModel):
    root: list[ScheduleItem] = Field(default_factory=list, description="Schedule items.")
