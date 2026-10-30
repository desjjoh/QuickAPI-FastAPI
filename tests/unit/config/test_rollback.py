import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from scripts import test_rollback as rollback

pytestmark = pytest.mark.unit
SOURCE = 'https://github.com/desjjoh/QuickAPI-FastAPI'
CURRENT = 'ghcr.io/desjjoh/quickapi-fastapi@sha256:' + 'a' * 64
PREVIOUS = 'ghcr.io/desjjoh/quickapi-fastapi@sha256:' + 'b' * 64


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('REGISTRY', raising=False)
    monkeypatch.delenv('IMAGE_REPOSITORY', raising=False)


@pytest.mark.parametrize(
    'reference',
    [
        'ghcr.io/desjjoh/quickapi-fastapi:latest',
        'ghcr.io/other/application@sha256:' + 'a' * 64,
        CURRENT,
    ],
)
def test_invalid_or_identical_references_block(reference: str) -> None:
    with pytest.raises(ValueError):
        rollback.validate_references(CURRENT, reference, SOURCE)


def test_two_retained_digest_references_are_accepted() -> None:
    rollback.validate_references(CURRENT, PREVIOUS, SOURCE)


@pytest.mark.parametrize(
    'failure',
    [
        '',
        'schema',
        'identity',
        'same_revision',
        'schema_probe',
        'rollback_start',
        'rollback_write',
        'recovery_write',
        'same_container',
        'database_replaced',
        'cleanup',
    ],
)
def test_rollback_ordering_identity_and_failure_cleanup(
    failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    starts = 0

    def run(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal starts
        environment = dict(kwargs.get('env') or {})

        calls.append((arguments, environment))

        if '--force-recreate' in arguments:
            starts += 1

        if arguments[:3] == ['docker', 'image', 'inspect']:
            reference = arguments[-1]
            revision = (
                'a' if reference == CURRENT or failure == 'same_revision' else 'b'
            ) * 40
            result = json.dumps(
                [
                    {
                        'RepoDigests': [reference],
                        'Config': {
                            'User': '10001:10001',
                            'Labels': {
                                'org.opencontainers.image.source': (
                                    SOURCE if failure != 'identity' else 'other'
                                ),
                                'org.opencontainers.image.version': '1.3.0',
                                'org.opencontainers.image.revision': revision,
                            },
                        },
                    }
                ]
            )
        elif rollback.HEADS in arguments:
            result = json.dumps(
                [
                    (
                        'other-head'
                        if failure == 'schema' and PREVIOUS in arguments
                        else '0003_request_idempotency'
                    )
                ]
            )
        elif '{{.State.ExitCode}}' in arguments:
            result = '0'
        elif '{{.Config.Image}}' in arguments:
            result = PREVIOUS if starts == 2 else CURRENT
        elif 'ps' in arguments:
            if arguments[-1] == 'mysql-rollback':
                result = (
                    'changed-db'
                    if failure == 'database_replaced' and starts == 2
                    else 'same-db'
                )
            else:
                result = 'api-1' if failure == 'same_container' else f'api-{starts}'
        elif rollback.RESTART_SEED in arguments:
            result = 'seed-state'
        elif rollback.ROLLBACK_WRITES in arguments:
            assert arguments[-1] == 'seed-state'

            result = 'rollback-state'
        elif rollback.RECOVERY_WRITES in arguments:
            assert arguments[-1] == 'rollback-state'

            result = 'Recovered'
        else:
            result = 'Application exited (code 0)'

        failed = (
            (
                failure == 'schema_probe'
                and rollback.CHECK_SCHEMA in arguments
                and starts == 1
            )
            or (
                failure == 'rollback_start'
                and '--force-recreate' in arguments
                and starts == 2
            )
            or (failure == 'rollback_write' and rollback.ROLLBACK_WRITES in arguments)
            or (failure == 'recovery_write' and rollback.RECOVERY_WRITES in arguments)
            or (failure == 'cleanup' and 'down' in arguments)
        )

        return subprocess.CompletedProcess(
            arguments, 1 if failed else 0, stdout=result, stderr=''
        )

    monkeypatch.setattr(rollback, 'ROOT', tmp_path)
    monkeypatch.setattr(rollback.subprocess, 'run', run)

    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            rollback.qualify(CURRENT, PREVIOUS, SOURCE)
    else:
        rollback.qualify(CURRENT, PREVIOUS, SOURCE)

    record = json.loads((tmp_path / 'test-artifacts/rollback/result.json').read_text())

    assert record['passed'] is (not failure)

    if failure in {'schema', 'identity', 'same_revision'}:
        assert not any('compose' in arguments for arguments, _ in calls)
    else:
        assert calls[-1][0][-3:] == ['down', '--volumes', '--remove-orphans']
        assert all('quickapi-fastapi-dev' not in arguments for arguments, _ in calls)

    if not failure:
        migrations = [arguments for arguments, _ in calls if 'migrate' in arguments]
        transitions = [
            environment['ROLLBACK_ACTIVE_IMAGE']
            for arguments, environment in calls
            if '--force-recreate' in arguments
        ]

        assert len(migrations) == 1
        assert transitions == [CURRENT, PREVIOUS, CURRENT]
        assert sum(rollback.CHECK_SCHEMA in arguments for arguments, _ in calls) == 3
        assert len(record['transitions']) == 3
        assert sum(rollback.RUNTIME_CHECKS in arguments for arguments, _ in calls) == 2
        assert (
            sum(rollback.RETAINED_IDENTITY in arguments for arguments, _ in calls) == 1
        )


def test_rollback_workflow_has_no_publication_or_database_downgrade() -> None:
    root = Path(__file__).resolve().parents[3]
    document = yaml.load(
        (root / '.github/workflows/rollback-check.yml').read_text(),
        Loader=yaml.BaseLoader,
    )

    assert set(document['on']) == {'workflow_dispatch'}
    assert document['permissions']['packages'] == 'read'
    assert document['jobs']['rollback']['if'] == "github.ref == 'refs/heads/main'"

    steps = document['jobs']['rollback']['steps']

    assert not any(
        'publish' in step.get('run', '') or 'downgrade' in step.get('run', '')
        for step in steps
    )
    assert steps[-1]['if'] == 'always()'
    assert steps[-1]['with']['retention-days'] == '90'

    compose = yaml.load(
        (root / 'docker-compose.rollback.yml').read_text(), Loader=yaml.BaseLoader
    )

    assert 'ports' not in compose['services']['api']
    assert 'ports' not in compose['services']['mysql-rollback']
    assert compose['services']['mysql-rollback']['tmpfs'] == ['/var/lib/mysql']


@pytest.mark.parametrize('stage', ['rollback', 'recovery'])
@pytest.mark.parametrize('fault', ['', 'replay', 'write'])
def test_http_state_replay_and_cross_image_writes(stage: str, fault: str) -> None:
    item = {'id': 'original', 'name': 'Retained update', 'version': 2}
    created = {'id': 'rollback-created', 'name': 'Rollback-created item', 'version': 1}
    original = b'{"id":"original","version":1}'
    state: dict[str, Any] = {
        'item': item,
        'body': {'name': 'Restart persistence', 'price': 12.34},
        'key': 'container-replacement-create',
        'status': 201,
        'response': base64.b64encode(original).decode(),
        'collection': {'data': [item], 'total': 1},
    }

    if stage == 'recovery':
        state['item'] = item | {'name': 'Written during rollback', 'version': 3}
        state['rollbackItem'] = created
        state['collection'] = {'data': [state['item'], created], 'total': 2}

    responses: list[tuple[int, bytes]] = [
        (200, b''),
        (200, b''),
        (200, json.dumps(state['item']).encode()),
        (201, original),
        (200, json.dumps(state['item']).encode()),
        (200, json.dumps(state['collection']).encode()),
    ]

    if stage == 'rollback':
        responses.extend(
            [
                (
                    200,
                    json.dumps(
                        item | {'name': 'Written during rollback', 'version': 3}
                    ).encode(),
                ),
                (201, json.dumps(created).encode()),
                (200, b'{"data":[],"total":2}'),
            ]
        )
        program = rollback.ROLLBACK_WRITES
    else:
        responses.extend(
            [
                (200, json.dumps(created).encode()),
                (200, b'{"name":"Recovered current image","version":4}'),
                (200, b'{}'),
                (200, b'{}'),
                (404, b'{}'),
                (404, b'{}'),
            ]
        )
        program = rollback.RECOVERY_WRITES

    if fault == 'replay':
        responses[3] = (201, b'{"different":"response"}')
    elif fault == 'write':
        responses[6 if stage == 'rollback' else 7] = (409, b'{}')

    calls: list[tuple[str, str, object, str | None]] = []

    def call(
        path: str, method: str = 'GET', body: object = None, key: str | None = None
    ) -> tuple[int, bytes]:
        calls.append((path, method, body, key))

        return responses.pop(0)

    def execute() -> None:
        exec(
            compile(
                program.removeprefix(rollback.HTTP_CLIENT), '<rollback-http>', 'exec'
            ),
            {
                'json': json,
                'call': call,
                'sys': SimpleNamespace(argv=['check', json.dumps(state)]),
            },
        )

    if fault:
        with pytest.raises(AssertionError):
            execute()
    else:
        execute()

        assert not responses
        assert calls[3][3] == state['key']


def test_embedded_programs_compile() -> None:
    for name in (
        'HEADS',
        'CHECK_SCHEMA',
        'ROLLBACK_WRITES',
        'RECOVERY_WRITES',
        'RETAINED_IDENTITY',
    ):
        compile(getattr(rollback, name), name, 'exec')
