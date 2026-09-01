from typing import Any

import pytest
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.routing import Route

from app.config.application import create_app

pytestmark = pytest.mark.integration

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
ERROR_STATUSES = {"404", "422", "500", "503"}
ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}


@pytest.fixture(scope="module")
def application() -> FastAPI:
    return create_app()


@pytest.fixture(scope="module")
def schema(application: FastAPI) -> dict[str, Any]:
    return application.openapi()


def operations(schema: dict[str, Any]):
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def response_schema(
    response: dict[str, Any], media_type: str = "application/json"
) -> dict[str, Any]:
    return response["content"][media_type]["schema"]


def test_application_metadata_and_tags(schema: dict[str, Any]) -> None:
    assert schema["openapi"].startswith("3.1.")
    assert schema["info"] == {
        "title": "QuickAPI",
        "description": "A production-oriented example API built with FastAPI.",
        "version": "1.0.0",
    }
    assert schema["tags"] == [
        {"name": "System", "description": "Runtime and service diagnostics."},
        {"name": "Items", "description": "CRUD operations for items."},
    ]


def test_documentation_and_all_unversioned_routes_are_registered(
    application: FastAPI, schema: dict[str, Any]
) -> None:
    registered: set[str] = {
        route.path for route in application.routes if isinstance(route, Route)
    }
    assert {"/docs", "/redoc", "/openapi.json"} <= registered
    assert {path for path in schema["paths"] if not path.startswith("/api/")} == {
        "/",
        "/health",
        "/ready",
        "/info",
        "/system",
        "/metrics",
    }


def test_every_operation_has_identity_and_declared_error_contracts(
    schema: dict[str, Any],
) -> None:
    seen_ids: set[str] = set()
    for path, method, operation in operations(schema):
        assert operation["tags"] in (["System"], ["Items"])
        assert operation["summary"] and operation["description"]
        operation_id = operation["operationId"]
        assert operation_id not in seen_ids
        seen_ids.add(operation_id)

        assert "500" in operation["responses"], (method, path)
        for status, response in operation["responses"].items():
            if status in ERROR_STATUSES:
                expected = (
                    {"$ref": "#/components/schemas/ReadyResponse"}
                    if (path, status) == ("/ready", "503")
                    else ERROR_REF
                )
                assert response_schema(response) == expected, (method, path, status)


def test_validation_error_names_alias_the_shared_envelope(
    schema: dict[str, Any],
) -> None:
    schemas = schema["components"]["schemas"]
    expected: dict[str, Any] = {
        "type": "object",
        "required": ["status", "message", "timestamp"],
    }
    assert schemas["ValidationError"] == ERROR_REF
    assert schemas["HTTPValidationError"] == ERROR_REF
    assert {key: schemas["ErrorResponse"][key] for key in expected} == expected
    properties = schemas["ErrorResponse"]["properties"]
    assert properties["status"]["type"] == "integer"
    assert properties["message"]["type"] == "string"
    assert properties["timestamp"]["type"] == "integer"


def test_item_operation_parameters_and_request_bodies(schema: dict[str, Any]) -> None:
    collection = schema["paths"]["/api/v1/items/"]
    query = {
        parameter["name"]: parameter for parameter in collection["get"]["parameters"]
    }
    assert set(query) == {
        "page",
        "limit",
        "order",
        "search",
        "sort",
        "min_price",
        "max_price",
    }
    assert query["page"]["schema"]["minimum"] == 1
    assert query["limit"]["schema"]["minimum"] == 1
    assert query["limit"]["schema"]["maximum"] == 100
    assert query["order"]["schema"]["enum"] == ["asc", "desc"]
    assert query["sort"]["schema"]["enum"] == ["name", "price", "created_at"]
    assert collection["post"]["requestBody"] == {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ItemBase"}}
        },
        "required": True,
    }

    member = schema["paths"]["/api/v1/items/{id}"]
    for method in ("get", "patch", "put", "delete"):
        parameter = member[method]["parameters"][0]
        assert (parameter["name"], parameter["in"], parameter["required"]) == (
            "id",
            "path",
            True,
        )
        assert parameter["schema"]["pattern"] == "^[0-9a-f]{16}$"
        assert (
            parameter["schema"]["minLength"] == parameter["schema"]["maxLength"] == 16
        )
    assert response_schema(member["get"]["responses"]["404"]) == ERROR_REF
    assert response_schema(schema["paths"]["/ready"]["get"]["responses"]["503"]) == {
        "$ref": "#/components/schemas/ReadyResponse"
    }


def test_success_and_pagination_schemas(schema: dict[str, Any]) -> None:
    expected = {
        ("/", "get", "200"): "RootResponse",
        ("/health", "get", "200"): "HealthResponse",
        ("/ready", "get", "200"): "ReadyResponse",
        ("/info", "get", "200"): "InfoResponse",
        ("/system", "get", "200"): "SystemResponse",
        ("/api/v1/items/", "post", "201"): "ItemResponse",
        ("/api/v1/items/", "get", "200"): "PaginatedResult_ItemResponse_",
        ("/api/v1/items/{id}", "get", "200"): "ItemResponse",
        ("/api/v1/items/{id}", "patch", "200"): "ItemResponse",
        ("/api/v1/items/{id}", "put", "200"): "ItemResponse",
        ("/api/v1/items/{id}", "delete", "200"): "ItemResponse",
    }
    for (path, method, status), model in expected.items():
        assert response_schema(schema["paths"][path][method]["responses"][status]) == {
            "$ref": f"#/components/schemas/{model}"
        }

    pagination = schema["components"]["schemas"]["PaginatedResult_ItemResponse_"]
    assert pagination["required"] == ["data", "total", "page", "limit"]
    assert pagination["properties"]["data"]["items"] == {
        "$ref": "#/components/schemas/ItemResponse"
    }
    assert all(
        pagination["properties"][key]["type"] == "integer"
        for key in ("total", "page", "limit")
    )


def test_operational_json_contracts_are_strict_and_complete(
    schema: dict[str, Any],
) -> None:
    schemas = schema["components"]["schemas"]
    required = {
        "RootResponse": {"message"},
        "HealthResponse": {"alive", "status", "uptime", "timestamp"},
        "ReadyResponse": {"ready", "status", "timestamp", "checks"},
        "ReadyCheck": {"name", "status", "response_time_ms"},
        "InfoResponse": {
            "name",
            "version",
            "environment",
            "hostname",
            "pid",
            "python_version",
            "platform",
            "architecture",
            "started_at",
            "timezone",
        },
        "SystemResponse": {
            "uptime",
            "timestamp",
            "event_loop_lag",
            "db",
            "cpu",
            "memory",
            "process",
            "os",
        },
        "CpuDiagnostics": {"cores", "model", "load_average"},
        "MemoryDiagnostics": {
            "total_bytes",
            "available_bytes",
            "used_bytes",
            "percentage",
        },
        "ProcessDiagnostics": {
            "rss_bytes",
            "heap_total_bytes",
            "heap_used_bytes",
            "external_bytes",
            "active_handles",
        },
        "OsDiagnostics": {"platform", "release"},
    }
    for model, properties in required.items():
        assert schemas[model]["type"] == "object"
        assert schemas[model]["additionalProperties"] is False
        assert set(schemas[model]["required"]) == properties
        assert set(schemas[model]["properties"]) == properties

    health = schemas["HealthResponse"]["properties"]
    assert health["status"]["enum"] == ["alive", "dead"]
    assert health["uptime"]["minimum"] == 0
    assert health["timestamp"]["format"] == "date-time"

    ready = schemas["ReadyResponse"]["properties"]
    assert ready["status"]["enum"] == ["ready", "not_ready"]
    assert ready["timestamp"]["format"] == "date-time"
    assert ready["checks"]["items"] == {"$ref": "#/components/schemas/ReadyCheck"}
    check = schemas["ReadyCheck"]["properties"]
    assert check["name"]["minLength"] == 1
    assert check["status"]["enum"] == ["up", "down"]
    assert check["response_time_ms"]["minimum"] == 0

    info = schemas["InfoResponse"]["properties"]
    assert info["version"]["pattern"] == r"^\d+\.\d+\.\d+$"
    assert info["environment"]["enum"] == ["development", "production", "test"]
    assert info["pid"]["exclusiveMinimum"] == 0
    assert info["started_at"]["format"] == "date-time"
    for field in ("python_version", "platform", "architecture", "timezone"):
        assert info[field]["minLength"] == 1

    system = schemas["SystemResponse"]["properties"]
    assert system["db"]["enum"] == ["connected", "disconnected"]
    for field, model in {
        "cpu": "CpuDiagnostics",
        "memory": "MemoryDiagnostics",
        "process": "ProcessDiagnostics",
        "os": "OsDiagnostics",
    }.items():
        assert system[field] == {"$ref": f"#/components/schemas/{model}"}
    for field in ("uptime", "timestamp", "event_loop_lag"):
        assert system[field]["minimum"] == 0

    cpu = schemas["CpuDiagnostics"]["properties"]
    assert cpu["cores"]["minimum"] == 1
    assert cpu["model"]["minLength"] == 1
    assert cpu["load_average"]["minItems"] == 3
    assert cpu["load_average"]["maxItems"] == 3
    assert all(item["minimum"] == 0 for item in cpu["load_average"]["prefixItems"])

    memory = schemas["MemoryDiagnostics"]["properties"]
    for field in ("total_bytes", "available_bytes", "used_bytes", "percentage"):
        assert memory[field]["minimum"] == 0
    assert memory["percentage"]["maximum"] == 100

    process = schemas["ProcessDiagnostics"]["properties"]
    assert all(property_schema["minimum"] == 0 for property_schema in process.values())
    os_schema = schemas["OsDiagnostics"]["properties"]
    assert all(
        property_schema["minLength"] == 1 for property_schema in os_schema.values()
    )


def test_patch_nullable_and_required_representation(schema: dict[str, Any]) -> None:
    patch = schema["paths"]["/api/v1/items/{id}"]["patch"]
    assert patch["requestBody"]["required"] is True
    assert response_schema({"content": patch["requestBody"]["content"]}) == {
        "$ref": "#/components/schemas/UpdateItemRequest"
    }
    update = schema["components"]["schemas"]["UpdateItemRequest"]
    assert "required" not in update
    assert update["properties"]["name"]["type"] == "string"
    assert update["properties"]["price"]["type"] == "number"
    assert {
        entry["type"] for entry in update["properties"]["description"]["anyOf"]
    } == {"string", "null"}


def test_metrics_content_type(schema: dict[str, Any]) -> None:
    response = schema["paths"]["/metrics"]["get"]["responses"]["200"]
    assert set(response["content"]) == {CONTENT_TYPE_LATEST}
    assert "schema" not in response["content"][CONTENT_TYPE_LATEST]
