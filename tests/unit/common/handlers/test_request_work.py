import asyncio

import httpx
import pytest

from app.common.handlers.request_work import RequestWork
from app.config.application import create_app

pytestmark = pytest.mark.unit


async def test_quiesce_withdraws_readiness_and_rejects_new_work() -> None:
    app = create_app()

    app.state.lifecycle.quiesce()
    app.state.request_work.quiesce()
    assert not app.state.lifecycle.is_ready()
    assert app.state.lifecycle.is_alive()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        response = await client.get('/ready')

    assert response.status_code == 503
    assert response.headers['connection'] == 'close'
    assert response.json()['message'] == 'Application is shutting down.'


async def test_drain_waits_for_work_and_repeated_quiesce_keeps_deadline() -> None:
    work = RequestWork(0.2)
    release = asyncio.Event()
    task = asyncio.create_task(release.wait())

    work.track(task)
    work.quiesce()
    started = work.draining_at

    work.quiesce()
    assert work.draining_at == started
    drain = asyncio.create_task(work.drain())

    await asyncio.sleep(0)
    assert not drain.done()
    with pytest.raises(RuntimeError):
        work.resume()

    release.set()
    await drain
    assert not work.failed
    work.resume()
    assert work.draining_at is None


async def test_drain_expiry_cancels_work_and_reports_failure() -> None:
    work = RequestWork(0.01)
    task = asyncio.create_task(asyncio.Event().wait())

    work.track(task)
    await work.drain()
    assert work.failed
    with pytest.raises(asyncio.CancelledError):
        await task
