import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.common.models.parameters_model import EntityId

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "identifier",
    ["0123456789abcdef", "aaaaaaaaaaaaaaaa", 'ABCDEF0123456789', 'A1b2C3d4E5f6G7h8'],
)
async def test_accepts_sixteen_character_alphanumeric_ids(identifier: str) -> None:
    app = FastAPI()

    @app.get("/{identifier}")
    async def route(identifier: EntityId) -> str:
        return identifier

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/{identifier}")

    assert response.status_code == 200
    assert response.json() == identifier


@pytest.mark.parametrize(
    "identifier",
    ["abc", "0123456789abcdef0", "ABCDEF012345678_", "0123456789abcde-", 'é' * 16],
)
async def test_rejects_invalid_entity_ids(identifier: str) -> None:
    app = FastAPI()

    @app.get("/{identifier}")
    async def route(identifier: EntityId) -> str:
        return identifier

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/{identifier}")

    assert response.status_code == 422
