import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import test_image

pytestmark = pytest.mark.unit


def image_command_result(arguments: list[str], calls: list[list[str]]) -> str:
    replaced = any('--force-recreate' in call for call in calls)

    if arguments[:3] == ['docker', 'image', 'inspect']:
        return '10001:10001'

    if '{{.State.ExitCode}}' in arguments:
        return '0'

    if '{{.Image}}' in arguments:
        return 'sha256:test-image'

    if 'ps' in arguments:
        if arguments[-1] == 'mysql-smoke':
            return 'mysql-container-id'

        return 'replacement-container-id' if replaced else 'original-container-id'

    return 'Application exited (code 0)'


@pytest.mark.parametrize(
    'failure',
    [
        'database_start',
        'http_checks',
        'runtime_checks',
        'image_user',
        'artifact_write',
        'restart_seed',
        'replacement_start',
        'restart_checks',
        'same_container',
        'different_image',
        'database_replaced',
    ],
)
def test_image_failure_always_removes_disposable_project(
    failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if (
            (failure == 'database_start' and 'up' in arguments)
            or (failure == 'http_checks' and test_image.HTTP_CHECKS in arguments)
            or (failure == 'runtime_checks' and test_image.RUNTIME_CHECKS in arguments)
            or (failure == 'restart_seed' and test_image.RESTART_SEED in arguments)
            or (failure == 'restart_checks' and test_image.RESTART_CHECKS in arguments)
            or (failure == 'replacement_start' and '--force-recreate' in arguments)
        ):
            raise subprocess.CalledProcessError(
                1, arguments, output='Test failure', stderr='Test diagnostic'
            )

        result = image_command_result(arguments, calls)
        replaced = any('--force-recreate' in call for call in calls)

        if failure == 'image_user' and arguments[:3] == ['docker', 'image', 'inspect']:
            result = 'root'

        if failure == 'same_container' and 'ps' in arguments and arguments[-1] == 'api':
            result = 'original-container-id'

        if failure == 'different_image' and '{{.Image}}' in arguments and replaced:
            result = 'sha256:different-image'

        if (
            failure == 'database_replaced'
            and 'ps' in arguments
            and arguments[-1] == 'mysql-smoke'
            and replaced
        ):
            result = 'different-mysql-container'

        return subprocess.CompletedProcess(arguments, 0, stdout=result, stderr='')

    monkeypatch.setattr(test_image, 'ROOT', tmp_path)
    monkeypatch.setattr(test_image.subprocess, 'run', run)
    if failure == 'artifact_write':

        def denied(*_: Any, **__: Any) -> None:
            raise PermissionError('Injected artifact failure')

        monkeypatch.setattr(Path, 'write_text', denied)

    with pytest.raises((subprocess.CalledProcessError, PermissionError, RuntimeError)):
        test_image.qualify('quickapi-fastapi:test')

    assert calls[-1][-3:] == ['down', '--volumes', '--remove-orphans']
    assert 'quickapi-fastapi-smoke' in calls[-1]
    assert all('quickapi-fastapi-dev' not in command for command in calls)

    if failure == 'image_user':
        assert not any('up' in command for command in calls)

    if failure in {'same_container', 'different_image', 'database_replaced'}:
        assert not any(test_image.RESTART_CHECKS in command for command in calls)


@pytest.mark.parametrize(
    'failure',
    [
        'none',
        'retained_state',
        'replay_status',
        'replay_bytes',
        'duplicate_create',
        'fresh_write',
    ],
)
def test_restart_http_checks_reject_lost_state_and_duplicate_writes(
    failure: str,
) -> None:
    item = {'id': 'abcdefghijklmnop', 'name': 'Retained update', 'version': 2}
    original = b'{"id":"abcdefghijklmnop","name":"Restart persistence","version":1}'
    collection = {'data': [item], 'total': 1}
    state = {
        'item': item,
        'body': {'name': 'Restart persistence', 'price': 12.34},
        'key': 'container-replacement-create',
        'status': 201,
        'response': base64.b64encode(original).decode('ascii'),
        'collection': collection,
    }
    responses = [
        (200, b''),
        (200, b''),
        (200, json.dumps(item).encode()),
        (201, original),
        (200, json.dumps(item).encode()),
        (200, json.dumps(collection).encode()),
        (200, b'{"name":"After restart","version":3}'),
        (200, b'{}'),
        (404, b'{}'),
    ]

    if failure == 'retained_state':
        responses[2] = (404, b'{}')
    elif failure == 'replay_status':
        responses[3] = (200, original)
    elif failure == 'replay_bytes':
        responses[3] = (201, json.dumps(json.loads(original)).encode())
    elif failure == 'duplicate_create':
        responses[5] = (200, b'{"data":[],"total":2}')
    elif failure == 'fresh_write':
        responses[6] = (409, b'{}')

    calls: list[tuple[str, str, object, str | None]] = []

    def call(
        path: str, method: str = 'GET', body: object = None, key: str | None = None
    ) -> tuple[int, bytes]:
        calls.append((path, method, body, key))

        return responses.pop(0)

    def execute() -> None:
        exec(
            compile(
                test_image.RESTART_CHECKS.removeprefix(test_image.HTTP_CLIENT),
                '<restart-checks>',
                'exec',
            ),
            {
                'call': call,
                'json': json,
                'sys': SimpleNamespace(argv=['check', json.dumps(state)]),
            },
        )

    if failure == 'none':
        execute()

        assert not responses
        assert calls[3] == ('/api/v1/items', 'POST', state['body'], state['key'])
        assert calls[6][2] == {'name': 'After restart', 'expected_version': 2}
    else:
        with pytest.raises(AssertionError):
            execute()


def test_image_checks_runtime_before_http_and_stops_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        result = image_command_result(arguments, calls)

        return subprocess.CompletedProcess(arguments, 0, stdout=result, stderr='')

    monkeypatch.setattr(test_image, 'ROOT', tmp_path)
    monkeypatch.setattr(test_image.subprocess, 'run', run)

    test_image.qualify('quickapi-fastapi:test')

    runtime = next(
        i for i, call in enumerate(calls) if test_image.RUNTIME_CHECKS in call
    )
    http = next(i for i, call in enumerate(calls) if test_image.HTTP_CHECKS in call)

    assert runtime < http
    seed = next(i for i, call in enumerate(calls) if test_image.RESTART_SEED in call)
    recreate = next(i for i, call in enumerate(calls) if '--force-recreate' in call)
    recovery = next(
        i for i, call in enumerate(calls) if test_image.RESTART_CHECKS in call
    )

    assert http < seed < recreate < recovery
    assert calls[recreate][-4:] == ['--wait', '--no-deps', '--force-recreate', 'api']
    assert sum('stop' in call for call in calls) == 2
    assert sum('run' in call and 'migrate' in call for call in calls) == 1
    assert calls[recovery][-1] == 'Application exited (code 0)'
    assert (tmp_path / 'test-artifacts/production-mysql.log').read_text().count(
        'Application exited (code 0)'
    ) == 3
    assert calls[-1][-3:] == ['down', '--volumes', '--remove-orphans']
