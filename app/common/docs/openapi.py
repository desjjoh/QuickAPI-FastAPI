from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def configure_custom_validation_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            tags=app.openapi_tags,
            routes=app.routes,
        )

        error_ref: dict[str, str] = {"$ref": "#/components/schemas/ErrorResponse"}

        schema["components"]["schemas"]["ValidationError"] = error_ref
        schema["components"]["schemas"]["HTTPValidationError"] = error_ref

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
                        responses["422"]["content"]["application/json"][
                            "schema"
                        ] = error_ref

                    responses.setdefault(
                        "500",
                        {
                            "description": "Unexpected server error.",
                            "content": {"application/json": {"schema": error_ref}},
                        },
                    )

        app.openapi_schema = schema
        return app.openapi_schema

    setattr(app, "openapi", custom_openapi)
