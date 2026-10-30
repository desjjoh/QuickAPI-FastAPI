import asyncio
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason='Real POSIX signals and reload supervisor qualification runs on Linux',
)
@pytest.mark.parametrize('reload', [False, True])
async def test_native_entrypoint_handles_sigterm(
    reload: bool, database_engine: AsyncEngine, tmp_path: Path
) -> None:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    env = {
        **os.environ,
        'ENV': 'development' if reload else 'production',
        'HOST': '127.0.0.1',
        'PORT': str(port),
        'LOG_LEVEL': 'DEBUG',
        'DATABASE_URL': database_engine.url.render_as_string(hide_password=False),
        'HTTP_DRAIN_TIMEOUT_MS': '700',
        'SHUTDOWN_TIMEOUT_MS': '2000',
    }
    log_path = tmp_path / 'native.log'

    with log_path.open('w') as logs:
        process = subprocess.Popen(
            [sys.executable, '-m', 'app.main'],
            env=env,
            stdout=logs,
            stderr=subprocess.STDOUT,
        )

        try:
            async with httpx.AsyncClient(
                base_url=f'http://127.0.0.1:{port}', timeout=1
            ) as client:
                async with asyncio.timeout(10):
                    while True:
                        assert process.poll() is None, log_path.read_text()

                        try:
                            if (await client.get('/ready')).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass

                        await asyncio.sleep(0.03)

            process.send_signal(signal.SIGTERM)

            try:
                await asyncio.to_thread(process.wait, timeout=8)
            except subprocess.TimeoutExpired:
                pytest.fail("Native shutdown timed out: " + log_path.read_text())

            assert process.returncode in (0, -signal.SIGTERM), log_path.read_text()
            assert 'Application exited cleanly' in log_path.read_text()
            with pytest.raises(OSError):
                await asyncio.open_connection('127.0.0.1', port)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


async def wait_file(path: Path) -> None:
    async with asyncio.timeout(5):
        while not path.exists():
            await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    'mode',
    [
        'idle',
        'mutation',
        'stream',
        'late',
        'disconnect',
        'stuck',
        'blocked',
        'cleanup-failure',
        'cleanup-stuck',
        'repeated',
        'transaction-expired',
        'transaction-stuck',
    ],
)
async def test_shutdown_process_contract(
    mode: str, database_engine: AsyncEngine, tmp_path: Path
) -> None:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    env = {
        **os.environ,
        'ENV': 'production',
        'HOST': '127.0.0.1',
        'PORT': str(port),
        'DATABASE_URL': database_engine.url.render_as_string(hide_password=False),
        'SHUTDOWN_TEST_MODE': mode,
        'LOG_LEVEL': 'DEBUG',
        'SHUTDOWN_TEST_DIR': str(tmp_path),
        'HTTP_DRAIN_TIMEOUT_MS': '700',
        'SHUTDOWN_TIMEOUT_MS': '2000',
        'REQUEST_TIMEOUT_MS': (
            '150'
            if mode in {'late', 'transaction-expired', 'transaction-stuck'}
            else '10000'
        ),
        'REQUEST_FIRST_BODY_TIMEOUT_MS': '100',
        'REQUEST_CHUNK_TIMEOUT_MS': '100',
    }
    # cwd is the repository; module resolution uses PYTHONPATH rather than adding test code to the image.
    env['PYTHONPATH'] = str(Path.cwd())
    output = tmp_path / 'process.log'

    with output.open('w') as log:
        process = subprocess.Popen(
            [sys.executable, '-m', 'tests.fixtures.shutdown_server'],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        request: asyncio.Task[httpx.Response] | None = None

        try:
            async with (
                httpx.AsyncClient(
                    base_url=f'http://127.0.0.1:{port}', timeout=5
                ) as client,
                httpx.AsyncClient(timeout=1) as newcomer,
            ):
                async with asyncio.timeout(8):
                    while True:
                        assert process.poll() is None, output.read_text()

                        try:
                            if (await client.get('/ready')).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass

                        await asyncio.sleep(0.02)

                if mode in {
                    'mutation',
                    'stream',
                    'late',
                    'disconnect',
                    'stuck',
                    'blocked',
                    'transaction-expired',
                    'transaction-stuck',
                }:
                    request = asyncio.create_task(
                        client.post('/mutation', json={})
                        if mode.startswith('transaction-')
                        else client.get('/stream' if mode == 'stream' else '/work')
                    )

                    await wait_file(tmp_path / 'entered')

                if mode in {'late', 'transaction-expired', 'transaction-stuck'}:
                    assert request is not None and (await request).status_code == 408
                    assert not (tmp_path / 'finished').exists()
                    if mode.startswith('transaction-'):
                        assert not (tmp_path / 'dependency-closed').exists()

                if mode == 'disconnect':
                    assert request is not None
                    request.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await request

                if mode != 'blocked':
                    if sys.platform != 'win32':
                        process.send_signal(signal.SIGTERM)
                    else:
                        # Windows terminate() is a hard kill, not a graceful SIGTERM.
                        (tmp_path / 'stop').touch()

                await asyncio.sleep(0.15)
                if mode in {
                    'mutation',
                    'stream',
                    'late',
                    'transaction-expired',
                    'transaction-stuck',
                }:
                    assert not (tmp_path / 'cleanup').exists()
                    if mode.startswith('transaction-'):
                        assert not (tmp_path / 'dependency-closed').exists()

                if mode in {'mutation', 'stream', 'late', 'transaction-expired'}:
                    # A fresh connection is refused or rejected while accepted
                    # work still owns the database and is allowed to finish.
                    rejected = asyncio.create_task(
                        newcomer.get(f'http://127.0.0.1:{port}/health')
                    )

                    await asyncio.sleep(0)
                    (tmp_path / 'release').touch()
                    await wait_file(tmp_path / 'finished')

                    try:
                        refused = await rejected

                        assert refused.status_code == 503
                    except httpx.TransportError:
                        pass

                if mode == 'repeated':
                    await wait_file(tmp_path / 'cleanup')
                    if sys.platform != 'win32':
                        process.send_signal(signal.SIGTERM)
                    else:
                        (tmp_path / 'stop').touch()

                async with asyncio.timeout(6):
                    while process.poll() is None:
                        await asyncio.sleep(0.02)

                if request is not None:
                    responses = await asyncio.gather(request, return_exceptions=True)

                    if mode in {'mutation', 'stream'}:
                        response = responses[0]

                        assert (
                            isinstance(response, httpx.Response)
                            and response.status_code == 200
                        )
                        if mode == 'stream':
                            assert response.content == b'first\nlast\n'

            logs = output.read_text()
            forced = mode in {
                'stuck',
                'blocked',
                'cleanup-failure',
                'cleanup-stuck',
                'repeated',
                'transaction-stuck',
            }

            if forced:
                assert process.returncode == 1, logs
                assert 'Application exited cleanly' not in logs
                if mode == 'transaction-stuck':
                    assert 'Final shutdown deadline exceeded' in logs
                    assert not (tmp_path / 'dependency-closed').exists()
                    assert not (tmp_path / 'cleanup').exists()
            else:
                assert process.returncode in (0, -signal.SIGTERM), logs
                assert 'Application exited cleanly' in logs

            async with database_engine.connect() as connection:
                count = await connection.scalar(
                    text("SELECT COUNT(*) FROM items WHERE id='shutdown-test'")
                )

            assert count == (1 if mode == 'mutation' else 0)
            if mode.startswith('transaction-'):
                connection_id = int((tmp_path / 'connection-id').read_text())

                async with asyncio.timeout(3):
                    while True:
                        async with database_engine.connect() as connection:
                            processes = (
                                (await connection.execute(text('SHOW PROCESSLIST')))
                                .mappings()
                                .all()
                            )

                        if not any(
                            int(row['Id']) == connection_id for row in processes
                        ):
                            break

                        await asyncio.sleep(0.01)

                if mode == 'transaction-expired':
                    assert (tmp_path / 'dependency-closed').exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

            if request is not None:
                request.cancel()
                await asyncio.gather(request, return_exceptions=True)
