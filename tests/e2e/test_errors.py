import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST

from app.config.application import create_app

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_http_and_unexpected_error_envelopes(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    assert (await client.get("/does-not-exist")).json()["status"] == 404
    router = APIRouter()

    @router.get("/expected")
    async def expected() -> None:
        raise HTTPException(409, "conflict")

    @router.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret")

    app.include_router(router)
    expected_response = await client.get("/expected")
    assert (
        expected_response.status_code == 409
        and expected_response.json()["message"] == "conflict"
    )
    unexpected_response = await client.get("/unexpected")
    assert unexpected_response.status_code == 500
    assert unexpected_response.json()["message"] == "Internal server error."


def test_openapi_schema_and_documented_responses() -> None:
    schema = create_app().openapi()
    assert schema["info"]["title"] == "QuickAPI"
    item = schema["paths"]["/api/v1/items/{id}"]
    assert "404" in item["get"]["responses"]
    assert item["get"]["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert schema["components"]["schemas"]["HTTPValidationError"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    metrics = schema["paths"]["/metrics"]["get"]["responses"]["200"]
    assert set(metrics["content"]) == {CONTENT_TYPE_LATEST}
    assert "schema" not in metrics["content"][CONTENT_TYPE_LATEST]
