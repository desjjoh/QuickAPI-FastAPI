import asyncio
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from sqlalchemy import text

from app.common.handlers.database_pool import BoundedAsyncPool, DatabaseUnavailableError
from app.config.database_transport import DatabasePolicy, build_database_engine
from app.config.migrations import upgrade_connection
from scripts.test_database_support import TestDatabaseConfig as TargetConfig
from scripts.test_database_support import guarded_connection, load_test_config

pytestmark = [pytest.mark.integration, pytest.mark.database_tls]


def assert_certificate_failure(error: BaseException) -> None:
    current: BaseException | None = error
    for _ in range(8):
        if isinstance(current, ssl.SSLCertVerificationError):
            return
        if current is None:
            break
        current = current.__cause__ or current.__context__
    pytest.fail(
        'Expected certificate verification failure, not an unrelated connection failure'
    )


async def test_native_application_entrypoint_supports_verified_tls(
    tls_target: tuple[TargetConfig, DatabasePolicy],
) -> None:
    config, policy = tls_target
    engine = build_database_engine(config.url, policy=policy)
    try:
        async with guarded_connection(engine, config) as connection:
            await connection.run_sync(upgrade_connection)
            await connection.commit()
    finally:
        await engine.dispose()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        'APP_NAME': 'TLS test',
        'APP_VERSION': '1.0.0',
        'ENV': 'production',
        'HOST': '127.0.0.1',
        'PORT': str(port),
        'DATABASE_URL': config.url.render_as_string(hide_password=False),
        'DB_SSL': 'true',
        'DB_SSL_CA_FILE': policy.ca_file or '',
    }
    migrated = subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    process = subprocess.Popen(
        [sys.executable, '-m', 'app.main'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for _ in range(60):
            if process.poll() is not None:
                output, _ = process.communicate(timeout=1)
                pytest.fail('TLS application failed startup: ' + output)
            try:
                with urllib.request.urlopen(
                    f'http://127.0.0.1:{port}/ready', timeout=1
                ) as response:
                    assert response.status == 200
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail('TLS application did not become ready')
    finally:
        process.terminate()
        process.wait(timeout=10)
        if process.stdout is not None:
            process.stdout.close()


@pytest.fixture
def tls_target() -> tuple[TargetConfig, DatabasePolicy]:
    config = load_test_config()
    ca = os.environ['TEST_TLS_CA_FILE']
    return config, DatabasePolicy(
        ssl_enabled=True, ca_file=ca, acquire_timeout_ms=3000, connect_timeout_ms=2000
    )


@asynccontextmanager
async def relay(
    config: TargetConfig, *, stall: bool = False, bind: str = '127.0.0.1'
) -> AsyncGenerator[tuple[int, asyncio.Event, asyncio.Event], None]:
    requested = asyncio.Event()
    closed = asyncio.Event()
    tasks: set[asyncio.Task[None]] = set()

    async def peer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        current = asyncio.current_task()
        if current is not None:
            tasks.add(current)
        remote: asyncio.StreamWriter | None = None
        try:
            upstream, remote = await asyncio.open_connection(
                config.url.host, config.url.port
            )
            if stall:
                header = await upstream.readexactly(4)
                payload = await upstream.readexactly(
                    int.from_bytes(header[:3], 'little')
                )
                writer.write(header + payload)
                await writer.drain()
                header = await reader.readexactly(4)
                payload = await reader.readexactly(int.from_bytes(header[:3], 'little'))
                assert (
                    len(payload) == 32 and int.from_bytes(payload[:4], 'little') & 0x800
                )
                requested.set()
                while await reader.read(65536):
                    pass
            else:

                async def copy(
                    source: asyncio.StreamReader, target: asyncio.StreamWriter
                ) -> None:
                    while data := await source.read(65536):
                        target.write(data)
                        await target.drain()

                pipes = [
                    asyncio.create_task(copy(reader, remote)),
                    asyncio.create_task(copy(upstream, writer)),
                ]
                try:
                    await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in pipes:
                        task.cancel()
                    await asyncio.gather(*pipes, return_exceptions=True)
        finally:
            writer.close()
            if remote is not None:
                remote.close()
            await asyncio.gather(
                writer.wait_closed(),
                *([remote.wait_closed()] if remote is not None else []),
                return_exceptions=True,
            )
            closed.set()
            if current is not None:
                tasks.discard(current)

    server = await asyncio.start_server(peer, bind, 0)
    try:
        yield server.sockets[0].getsockname()[1], requested, closed
    finally:
        server.close()
        await server.wait_closed()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_verified_tls_connection_has_cipher(
    tls_target: tuple[TargetConfig, DatabasePolicy],
) -> None:
    config, policy = tls_target
    engine = build_database_engine(config.url, policy=policy)
    try:
        async with guarded_connection(engine, config) as connection:
            assert (await connection.execute(text('SELECT 1'))).scalar_one() == 1
            cipher = (
                await connection.execute(text("SHOW SESSION STATUS LIKE 'Ssl_cipher'"))
            ).one()
            assert cipher[1]
    finally:
        await engine.dispose()


async def test_wrong_ca_is_rejected(
    tls_target: tuple[TargetConfig, DatabasePolicy],
) -> None:
    config, policy = tls_target
    engine = build_database_engine(
        config.url,
        policy=replace(policy, ca_file=os.environ['TEST_TLS_UNTRUSTED_CA_FILE']),
    )
    try:
        with pytest.raises(DatabaseUnavailableError) as error:
            async with engine.connect():
                pass
        assert error.value.code == 'DB_CONNECTION_FAILED'
        assert_certificate_failure(error.value)
    finally:
        await engine.dispose()


async def test_wrong_server_identity_is_rejected(
    tls_target: tuple[TargetConfig, DatabasePolicy],
) -> None:
    config, policy = tls_target
    async with relay(config, bind='127.0.0.2') as (port, _, closed):
        engine = build_database_engine(
            config.url.set(host='127.0.0.2', port=port), policy=policy
        )
        try:
            with pytest.raises(DatabaseUnavailableError) as error:
                async with engine.connect():
                    pass
            assert_certificate_failure(error.value)
            await asyncio.wait_for(closed.wait(), 2)
        finally:
            await engine.dispose()


async def test_tls_negotiation_stall_obeys_connection_deadline_and_closes(
    tls_target: tuple[TargetConfig, DatabasePolicy],
) -> None:
    config, policy = tls_target
    async with relay(config, stall=True) as (port, requested, closed):
        engine = build_database_engine(
            config.url.set(host='127.0.0.1', port=port),
            policy=replace(policy, connect_timeout_ms=750, acquire_timeout_ms=3000),
        )
        try:
            with pytest.raises(DatabaseUnavailableError) as error:
                async with engine.connect():
                    pass
            assert requested.is_set() and error.value.code == 'DB_CONNECT_TIMEOUT'
            await asyncio.wait_for(closed.wait(), 2)
            assert (
                isinstance(engine.pool, BoundedAsyncPool)
                and engine.pool.admission.active == 0
            )
        finally:
            await engine.dispose()
