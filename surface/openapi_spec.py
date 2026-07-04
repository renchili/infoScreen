from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

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
)

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


def build_openapi() -> dict[str, Any]:
    schedule_list_schema = list_schema_for(ScheduleItem)
    object_schema = {"type": "object", "additionalProperties": True}

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "InfoScreen Local API",
            "version": "0.1.0",
            "description": "Local kiosk API for runtime dashboard JSON, refresh actions, market config, and local event search.",
        },
        "servers": [{"url": "http://127.0.0.1:8765", "description": "Local Surface kiosk server"}],
        "tags": [
            {"name": "dashboard", "description": "Static dashboard and runtime JSON"},
            {"name": "market", "description": "Market config and refresh APIs"},
            {"name": "local-events", "description": "Rendered DOM local event search APIs"},
            {"name": "media", "description": "Photo wall media endpoints"},
        ],
        "paths": {
            "/": {"get": {"tags": ["dashboard"], "summary": "Serve dashboard HTML", "description": "Returns sanitized dashboard HTML.", "responses": {"200": {"description": "HTML dashboard"}}}},
            "/index.html": {"get": {"tags": ["dashboard"], "summary": "Serve dashboard HTML", "description": "Same as GET /.", "responses": {"200": {"description": "HTML dashboard"}}}},
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
            "/api/market-refresh": {"post": {"tags": ["market"], "summary": "Refresh market runtime data", "description": "Runs surface/fetch_live_data.py.", "responses": {"200": json_response(ref("MarketRefreshResponse")), "500": json_response(ref("ErrorResponse"), "Refresh failed")}}},
            "/api/local-events/search": {
                "get": {"tags": ["local-events"], "summary": "Read latest local event search results", "description": "Returns runtime JSON without running a new search.", "responses": {"200": json_response(ref("LocalEventSearchResponse")), "404": json_response(ref("RuntimeMissingResponse"), "Runtime JSON missing")}},
                "post": {"tags": ["local-events"], "summary": "Run local event search for a location", "description": "Runs surface/search_local_events.py.", "requestBody": request_body(ref("LocalEventSearchRequest")), "responses": {"200": json_response(ref("LocalEventSearchResponse")), "500": json_response(ref("ErrorResponse"), "Search failed")}},
            },
            "/public_photos/{path}": {
                "get": {"tags": ["media"], "summary": "Serve a public photo file", "parameters": [{"name": "path", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Relative path under surface/.env/public_photos/."}], "responses": {"200": {"description": "Photo bytes"}, "404": {"description": "Not found"}}},
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
