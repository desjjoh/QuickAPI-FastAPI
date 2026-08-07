import httpx
import pytest

pytestmark = pytest.mark.e2e


async def test_favicon_returns_icon_bytes(client: httpx.AsyncClient) -> None:
    response = await client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/x-icon"
    assert response.content
