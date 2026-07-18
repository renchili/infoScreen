from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

try:
    from .api_models import (
        ErrorResponse,
        EventStreamResponse,
        LocalEventItem,
        LocalEventRuntimeInfo,
        LocalEventSearchRequest,
        LocalEventSearchResponse,
        LocalEventSourceDebug,
        LocalEventSourceSummary,
        MarketConfigRequest,
        MarketConfigResponse,
        MarketRefreshResponse,
        PhotoItem,
        PhotosResponse,
        RuntimeMissingResponse,
        ScheduleItem,
        StudioCaptureRequest,
        StudioCaptureResponse,
        StudioLatestTestResponse,
        StudioRuleBindingRequest,
        StudioRuleDeleteResponse,
        StudioRuleImportRequest,
        StudioRuleListResponse,
        StudioRuleResponse,
        StudioRuleRollbackRequest,
        StudioSnapshotListResponse,
        StudioSnapshotMetadata,
        StudioSourceListingState,
        StudioSourcesResponse,
        StudioSourceState,
        StudioTestAcceptedRow,
        StudioTestRejectedRow,
        StudioTestRequest,
        StudioTestResponse,
        StudioTestResult,
    )
    from .local_events_runtime.studio_rules import LocalEventStudioRule
except ImportError:
    from api_models import (
        ErrorResponse,
        EventStreamResponse,
        LocalEventItem,
        LocalEventRuntimeInfo,
        LocalEventSearchRequest,
        LocalEventSearchResponse,
        LocalEventSourceDebug,
        LocalEventSourceSummary,
        MarketConfigRequest,
        MarketConfigResponse,
        MarketRefreshResponse,
        PhotoItem,
        PhotosResponse,
        RuntimeMissingResponse,
        ScheduleItem,
        StudioCaptureRequest,
        StudioCaptureResponse,
        StudioLatestTestResponse,
        StudioRuleBindingRequest,
        StudioRuleDeleteResponse,
        StudioRuleImportRequest,
        StudioRuleListResponse,
        StudioRuleResponse,
        StudioRuleRollbackRequest,
        StudioSnapshotListResponse,
        StudioSnapshotMetadata,
        StudioSourceListingState,
        StudioSourcesResponse,
        StudioSourceState,
        StudioTestAcceptedRow,
        StudioTestRejectedRow,
        StudioTestRequest,
        StudioTestResponse,
        StudioTestResult,
    )
    from local_events_runtime.studio_rules import LocalEventStudioRule

OPENAPI_VERSION = "3.1.0"


def schema_for(model: Any) -> dict[str, Any]:
    return model.model_json_schema(ref_template="#/components/schemas/{model}")


def list_schema_for(item_type: Any) -> dict[str, Any]:
    return TypeAdapter(list[item_type]).json_schema(ref_template="#/components/schemas/{model}")


def ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def json_response(schema: dict[str, Any] | None = None, description: str = "OK") -> dict[str, Any]:
    content: dict[str, Any] = {"application/json": {}}
    if schema is not None:
        content["application/json"]["schema"] = schema
    return {"description": description, "content": content}


def request_body(schema: dict[str, Any], required: bool = True) -> dict[str, Any]:
    return {"required": required, "content": {"application/json": {"schema": schema}}}


def query_parameter(
    name: str,
    description: str,
    schema: dict[str, Any] | None = None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": schema or {"type": "string"},
    }


def build_openapi() -> dict[str, Any]:
    schedule_list_schema = list_schema_for(ScheduleItem)
    object_schema = {"type": "object", "additionalProperties": True}
    studio_binding_parameters = [
        query_parameter("source_id", "Configured Local Events source ID."),
        query_parameter("listing_url", "Configured official listing URL."),
    ]

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "InfoScreen Local API",
            "version": "0.4.0",
            "description": "Local kiosk API for runtime dashboard JSON, refresh actions, Local Event Studio snapshots, deterministic draft tests, and versioned rule publication.",
        },
        "servers": [{"url": "http://127.0.0.1:8765", "description": "Local Surface kiosk server"}],
        "tags": [
            {"name": "dashboard", "description": "Static dashboard and runtime JSON"},
            {"name": "market", "description": "Market config and refresh APIs"},
            {"name": "local-events", "description": "Rendered DOM local event search APIs"},
            {"name": "local-event-studio", "description": "Local rule, snapshot, test, publication, history, import, and export APIs"},
            {"name": "media", "description": "Photo wall media endpoints"},
        ],
        "paths": {
            "/": {"get": {"tags": ["dashboard"], "summary": "Serve dashboard HTML", "responses": {"200": {"description": "HTML dashboard"}}}},
            "/index.html": {"get": {"tags": ["dashboard"], "summary": "Serve dashboard HTML", "responses": {"200": {"description": "HTML dashboard"}}}},
            "/openapi.json": {"get": {"tags": ["dashboard"], "summary": "Return OpenAPI specification", "responses": {"200": json_response(None)}}},
            "/docs": {"get": {"tags": ["dashboard"], "summary": "Serve Swagger UI", "responses": {"200": {"description": "Swagger UI HTML"}}}},
            "/schedule.json": {"get": {"tags": ["dashboard"], "summary": "Read schedule runtime JSON", "responses": {"200": json_response(schedule_list_schema)}}},
            "/weather.json": {"get": {"tags": ["dashboard"], "summary": "Read weather runtime JSON", "responses": {"200": json_response(object_schema)}}},
            "/market.json": {"get": {"tags": ["market"], "summary": "Read market runtime JSON", "responses": {"200": json_response(object_schema)}}},
            "/market_config.json": {"get": {"tags": ["market"], "summary": "Read market config runtime JSON", "responses": {"200": json_response(ref("MarketConfigResponse"))}}},
            "/event_stream.json": {"get": {"tags": ["dashboard"], "summary": "Read event stream runtime JSON", "responses": {"200": json_response(ref("EventStreamResponse"))}}},
            "/photos.json": {"get": {"tags": ["media"], "summary": "Read photo wall runtime JSON", "responses": {"200": json_response(ref("PhotosResponse"))}}},
            "/sync_status.json": {"get": {"tags": ["dashboard"], "summary": "Read sync status runtime JSON", "responses": {"200": json_response(object_schema)}}},
            "/local_event_search_results.json": {"get": {"tags": ["local-events"], "summary": "Read local event runtime JSON", "responses": {"200": json_response(ref("LocalEventSearchResponse")), "404": json_response(ref("RuntimeMissingResponse"), "Runtime JSON missing")}}},
            "/api/market-config": {
                "get": {"tags": ["market"], "summary": "Read active market symbol config", "responses": {"200": json_response(ref("MarketConfigResponse"))}},
                "post": {"tags": ["market"], "summary": "Update active market symbol config", "requestBody": request_body(ref("MarketConfigRequest")), "responses": {"200": json_response(ref("MarketConfigResponse")), "400": json_response(ref("ErrorResponse"), "Invalid request")}},
            },
            "/api/market-refresh": {"post": {"tags": ["market"], "summary": "Refresh market runtime data", "responses": {"200": json_response(ref("MarketRefreshResponse")), "500": json_response(ref("ErrorResponse"), "Refresh failed")}}},
            "/api/local-events/search": {
                "get": {"tags": ["local-events"], "summary": "Read latest local event search results", "responses": {"200": json_response(ref("LocalEventSearchResponse")), "404": json_response(ref("RuntimeMissingResponse"), "Runtime JSON missing")}},
                "post": {"tags": ["local-events"], "summary": "Run local event search for a location", "requestBody": request_body(ref("LocalEventSearchRequest")), "responses": {"200": json_response(ref("LocalEventSearchResponse")), "500": json_response(ref("ErrorResponse"), "Search failed")}},
            },
            "/api/local-events/studio/sources": {
                "get": {"tags": ["local-event-studio"], "summary": "List configured sources and rule state", "responses": {"200": json_response(ref("StudioSourcesResponse")), "500": json_response(ref("ErrorResponse"), "Rule storage failed")}}
            },
            "/api/local-events/studio/rules": {
                "get": {"tags": ["local-event-studio"], "summary": "Read draft, published, and history rules", "parameters": studio_binding_parameters, "responses": {"200": json_response(ref("StudioRuleListResponse")), "400": json_response(ref("ErrorResponse"), "Invalid binding")}}
            },
            "/api/local-events/studio/draft": {
                "put": {"tags": ["local-event-studio"], "summary": "Save a validated draft rule", "requestBody": request_body(ref("LocalEventStudioRule")), "responses": {"200": json_response(ref("StudioRuleResponse")), "400": json_response(ref("ErrorResponse"), "Invalid rule")}},
                "delete": {"tags": ["local-event-studio"], "summary": "Delete the mutable draft only", "requestBody": request_body(ref("StudioRuleBindingRequest")), "responses": {"200": json_response(ref("StudioRuleDeleteResponse")), "400": json_response(ref("ErrorResponse"), "Invalid binding")}},
            },
            "/api/local-events/studio/test": {
                "post": {
                    "tags": ["local-event-studio"],
                    "summary": "Test the current draft against a stored snapshot",
                    "description": "Runs without external network access and stores accepted, rejected, and field-evidence rows under the machine-local Studio directory.",
                    "requestBody": request_body(ref("StudioTestRequest")),
                    "responses": {"200": json_response(ref("StudioTestResponse")), "400": json_response(ref("ErrorResponse"), "Invalid request"), "404": json_response(ref("ErrorResponse"), "Draft or snapshot missing"), "422": json_response(ref("ErrorResponse"), "Draft evaluation failed")},
                }
            },
            "/api/local-events/studio/test-latest": {
                "get": {
                    "tags": ["local-event-studio"],
                    "summary": "Read the latest test result for one source/listing",
                    "parameters": studio_binding_parameters,
                    "responses": {"200": json_response(ref("StudioLatestTestResponse")), "400": json_response(ref("ErrorResponse"), "Invalid binding")},
                }
            },
            "/api/local-events/studio/publish": {
                "post": {
                    "tags": ["local-event-studio"],
                    "summary": "Publish the tested current draft as the next version",
                    "description": "Publication is rejected unless the latest publishable snapshot test has the exact current draft fingerprint.",
                    "requestBody": request_body(ref("StudioRuleBindingRequest")),
                    "responses": {"200": json_response(ref("StudioRuleResponse")), "400": json_response(ref("ErrorResponse"), "Invalid binding"), "404": json_response(ref("ErrorResponse"), "Draft missing"), "409": json_response(ref("ErrorResponse"), "Version conflict"), "422": json_response(ref("ErrorResponse"), "Matching publishable test required")},
                }
            },
            "/api/local-events/studio/rollback": {
                "post": {"tags": ["local-event-studio"], "summary": "Republish a historical rule as a new version", "requestBody": request_body(ref("StudioRuleRollbackRequest")), "responses": {"200": json_response(ref("StudioRuleResponse")), "400": json_response(ref("ErrorResponse"), "Invalid request"), "404": json_response(ref("ErrorResponse"), "History version missing"), "409": json_response(ref("ErrorResponse"), "Version conflict")}}
            },
            "/api/local-events/studio/import": {
                "post": {"tags": ["local-event-studio"], "summary": "Import a validated rule as a draft", "requestBody": request_body(ref("StudioRuleImportRequest")), "responses": {"200": json_response(ref("StudioRuleResponse")), "400": json_response(ref("ErrorResponse"), "Invalid imported rule")}}
            },
            "/api/local-events/studio/export": {
                "get": {
                    "tags": ["local-event-studio"],
                    "summary": "Export a validated rule",
                    "parameters": studio_binding_parameters + [
                        query_parameter("status", "Rule state to export.", {"type": "string", "enum": ["draft", "published"], "default": "published"}, required=False),
                        query_parameter("version", "Historical version to export.", {"type": "integer", "minimum": 1}, required=False),
                    ],
                    "responses": {"200": json_response(ref("StudioRuleResponse")), "400": json_response(ref("ErrorResponse"), "Invalid query"), "404": json_response(ref("ErrorResponse"), "Rule missing")},
                }
            },
            "/api/local-events/studio/capture": {
                "post": {
                    "tags": ["local-event-studio"],
                    "summary": "Capture one configured official listing",
                    "description": "Runs the one-shot Studio capture job and stores screenshot, HTML, DOM evidence, and metadata.",
                    "requestBody": request_body(ref("StudioCaptureRequest")),
                    "responses": {"200": json_response(ref("StudioCaptureResponse")), "400": json_response(ref("ErrorResponse"), "Invalid source/listing"), "500": json_response(ref("ErrorResponse"), "Capture failed")},
                }
            },
            "/api/local-events/studio/snapshots": {
                "get": {
                    "tags": ["local-event-studio"],
                    "summary": "List stored official-list snapshots",
                    "parameters": [
                        query_parameter("source_id", "Optional source filter.", required=False),
                        query_parameter("listing_url", "Optional listing URL filter.", required=False),
                    ],
                    "responses": {"200": json_response(ref("StudioSnapshotListResponse")), "400": json_response(ref("ErrorResponse"), "Invalid filter")},
                }
            },
            "/api/local-events/studio/snapshot-asset": {
                "get": {
                    "tags": ["local-event-studio"],
                    "summary": "Read one stored snapshot asset",
                    "parameters": [
                        query_parameter("source_id", "Snapshot source ID."),
                        query_parameter("snapshot_id", "Snapshot ID."),
                        query_parameter("asset", "Asset name.", {"type": "string", "enum": ["page.png", "page.html", "dom.json", "metadata.json"]}),
                    ],
                    "responses": {"200": {"description": "Snapshot bytes"}, "400": json_response(ref("ErrorResponse"), "Invalid query"), "404": json_response(ref("ErrorResponse"), "Snapshot asset missing")},
                }
            },
            "/public_photos/{path}": {
                "get": {"tags": ["media"], "summary": "Serve a public photo file", "parameters": [{"name": "path", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Photo bytes"}, "404": {"description": "Not found"}}},
                "head": {"tags": ["media"], "summary": "Read public photo metadata", "parameters": [{"name": "path", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Photo metadata"}, "404": {"description": "Not found"}}},
            },
        },
        "components": {
            "schemas": {
                "ErrorResponse": schema_for(ErrorResponse),
                "RuntimeMissingResponse": schema_for(RuntimeMissingResponse),
                "MarketConfigRequest": schema_for(MarketConfigRequest),
                "MarketConfigResponse": schema_for(MarketConfigResponse),
                "MarketRefreshResponse": schema_for(MarketRefreshResponse),
                "LocalEventSearchRequest": schema_for(LocalEventSearchRequest),
                "LocalEventRuntimeInfo": schema_for(LocalEventRuntimeInfo),
                "LocalEventItem": schema_for(LocalEventItem),
                "LocalEventSourceSummary": schema_for(LocalEventSourceSummary),
                "LocalEventSourceDebug": schema_for(LocalEventSourceDebug),
                "LocalEventSearchResponse": schema_for(LocalEventSearchResponse),
                "LocalEventStudioRule": schema_for(LocalEventStudioRule),
                "StudioRuleBindingRequest": schema_for(StudioRuleBindingRequest),
                "StudioRuleRollbackRequest": schema_for(StudioRuleRollbackRequest),
                "StudioRuleImportRequest": schema_for(StudioRuleImportRequest),
                "StudioRuleResponse": schema_for(StudioRuleResponse),
                "StudioRuleDeleteResponse": schema_for(StudioRuleDeleteResponse),
                "StudioRuleListResponse": schema_for(StudioRuleListResponse),
                "StudioSourceListingState": schema_for(StudioSourceListingState),
                "StudioSourceState": schema_for(StudioSourceState),
                "StudioSourcesResponse": schema_for(StudioSourcesResponse),
                "StudioCaptureRequest": schema_for(StudioCaptureRequest),
                "StudioSnapshotMetadata": schema_for(StudioSnapshotMetadata),
                "StudioCaptureResponse": schema_for(StudioCaptureResponse),
                "StudioSnapshotListResponse": schema_for(StudioSnapshotListResponse),
                "StudioTestRequest": schema_for(StudioTestRequest),
                "StudioTestAcceptedRow": schema_for(StudioTestAcceptedRow),
                "StudioTestRejectedRow": schema_for(StudioTestRejectedRow),
                "StudioTestResult": schema_for(StudioTestResult),
                "StudioTestResponse": schema_for(StudioTestResponse),
                "StudioLatestTestResponse": schema_for(StudioLatestTestResponse),
                "EventStreamResponse": schema_for(EventStreamResponse),
                "PhotoItem": schema_for(PhotoItem),
                "PhotosResponse": schema_for(PhotosResponse),
                "ScheduleItem": schema_for(ScheduleItem),
            }
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(build_openapi(), ensure_ascii=False, indent=2))
