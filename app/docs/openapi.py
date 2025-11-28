from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def configure_custom_validation_openapi(app: FastAPI) -> None:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )

        error_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "status": {"type": "integer", "example": 422},
                "message": {
                    "type": "string",
                    "example": (
                        "Validation failed: name → Field required; "
                        "path.id → String should have at least 16 characters"
                    ),
                },
                "timestamp": {"type": "string", "format": "date-time"},
            },
            "required": ["status", "message", "timestamp"],
        }

        schema["components"]["schemas"]["ValidationError"] = error_schema
        schema["components"]["schemas"]["HTTPValidationError"] = error_schema

        paths: dict[str, Any] = schema.get("paths", {})

        for path_item_raw in paths.values():
            if not isinstance(path_item_raw, dict):
                continue

            path_item = cast(dict[str, Any], path_item_raw)

            for method_data_raw in path_item.values():
                if not isinstance(method_data_raw, dict):
                    continue

                method_data: dict[str, Any] = cast(dict[str, Any], method_data_raw)
                responses_raw = method_data.get("responses", {})

                if isinstance(responses_raw, dict):
                    responses = cast(dict[str, Any], responses_raw)

                    if "422" in responses:
                        del responses["422"]

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
