import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.common.models.parameters_model import HexId

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("identifier", ["0123456789abcdef", "aaaaaaaaaaaaaaaa"])
async def test_accepts_lowercase_sixteen_character_hex_ids(identifier: str) -> None:
    app = FastAPI()

    @app.get("/{identifier}")
    async def route(identifier: HexId) -> str:
        return identifier

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/{identifier}")
    assert response.status_code == 200
    assert response.json() == identifier


@pytest.mark.parametrize(
    "identifier", ["abc", "0123456789abcdef0", "ABCDEF0123456789", "0123456789abcdeg"]
)
async def test_rejects_invalid_hex_ids(identifier: str) -> None:
    app = FastAPI()

    @app.get("/{identifier}")
    async def route(identifier: HexId) -> str:
        return identifier

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/{identifier}")
    assert response.status_code == 422
