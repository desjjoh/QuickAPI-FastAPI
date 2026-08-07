import httpx
import pytest

pytestmark = pytest.mark.e2e


async def test_root_returns_exact_json_payload(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"message": "Hello World! Welcome to FastAPI!"}
