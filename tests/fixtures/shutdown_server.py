"""Subprocess-only shutdown faults; no test routes are installed in the product."""

import asyncio
import os
import signal
import socket
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import uvicorn
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.handlers.http_server import ApplicationServer
from app.config.application import create_app
from app.config.database import SessionLocal, get_session


def main() -> None:
    directory = Path(os.environ['SHUTDOWN_TEST_DIR'])
    mode = os.environ['SHUTDOWN_TEST_MODE']
    app = create_app()

    class Cleanup:
        name = 'test-cleanup'

        async def start(self) -> None:
            pass

        async def check(self) -> bool:
            return True

        async def stop(self) -> None:
            if (
                mode == 'transaction-expired'
                and not (directory / 'dependency-closed').exists()
            ):
                raise RuntimeError(
                    'Services stopped before transaction dependency cleanup'
                )

            (directory / 'cleanup').touch()
            if mode in {'cleanup-stuck', 'repeated'}:
                await asyncio.Event().wait()

            if mode == 'cleanup-failure':
                raise RuntimeError('Injected cleanup failure')

    app.state.lifecycle.register([Cleanup()])

    async def release() -> None:
        while not (directory / 'release').exists():
            await asyncio.sleep(0.01)

    async def tracked_session(
        session: AsyncSession = Depends(get_session),
    ) -> AsyncGenerator[AsyncSession, None]:
        try:
            yield session
        finally:
            (directory / 'dependency-closed').touch()

    router = APIRouter(route_class=ApplicationRoute)

    @router.post('/mutation')
    @transactional
    async def mutation(db: AsyncSession = Depends(tracked_session)) -> dict[str, bool]:
        identifier = await db.scalar(text('SELECT CONNECTION_ID()'))

        (directory / 'connection-id').write_text(str(identifier))
        await db.execute(
            text(
                "INSERT INTO items (id,name,price) VALUES ('shutdown-test','Shutdown',1.00)"
            )
        )
        (directory / 'entered').touch()
        if mode == 'transaction-stuck':
            while True:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass  # Final process deadline must bound an owned mutation.

        await release()
        (directory / 'finished').touch()

        return {'done': True}

    app.include_router(router)

    @app.get('/work')
    async def work() -> dict[str, bool]:
        if mode == 'blocked':
            (directory / 'entered').touch()
            # Start shutdown before blocking so the independent watchdog is armed.
            server.handle_exit(signal.SIGTERM, None)
            time.sleep(10)

        if mode in {'late', 'stuck'}:
            (directory / 'entered').touch()
            while True:
                try:
                    if mode == 'late':
                        await release()
                        break

                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass  # Deliberately adversarial work, verified by the watchdog.
        else:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(
                        text(
                            "INSERT INTO items (id,name,price) VALUES ('shutdown-test','Shutdown',1.00)"
                        )
                    )
                    (directory / 'entered').touch()
                    await release()

        (directory / 'finished').touch()

        return {'done': True}

    @app.get('/stream')
    async def stream() -> StreamingResponse:
        async def chunks() -> AsyncGenerator[bytes, None]:
            yield b'first\n'
            (directory / 'entered').touch()
            await release()
            yield b'last\n'
            (directory / 'finished').touch()

        return StreamingResponse(chunks())

    server = ApplicationServer(
        uvicorn.Config(
            app,
            host='127.0.0.1',
            port=int(os.environ['PORT']),
            ws='none',
            loop='app.config.event_loop:server_loop_factory',
            log_config=None,
            proxy_headers=False,
            access_log=False,
        )
    )

    async def control() -> None:
        while True:
            if (directory / 'stop').exists():
                (directory / 'stop').unlink()
                server.request_shutdown()

            await asyncio.sleep(0.01)

    original_startup = server.startup

    async def startup(sockets: list[socket.socket] | None = None) -> None:
        await original_startup(sockets)
        app.state.test_control = asyncio.create_task(control())

    server.startup = startup

    try:
        server.run()
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
