"""Qualify retained-image rollback against isolated disposable MySQL."""

import argparse
import json
import os
import re
import subprocess
from typing import Any

from scripts.release_source import SHA, VERSION
from scripts.security_policy import mapping, sequence
from scripts.security_scan import write_json
from scripts.test_database_support import ROOT, command_lock, load_test_config
from scripts.test_image import HTTP_CLIENT, RESTART_SEED, RUNTIME_CHECKS

RETAINED_IDENTITY = '''
import os
assert os.getuid() == 10001 and os.getgid() == 10001, 'Unexpected retained runtime identity'
'''

HEADS = '''
import json
from alembic.config import Config
from alembic.script import ScriptDirectory
print(json.dumps(ScriptDirectory.from_config(Config('/app/alembic.ini')).get_heads()))
'''

CHECK_SCHEMA = '''
from app.config.environment import settings
from app.config.database_transport import build_database_engine
from app.config.event_loop import run_database
from app.config.migrations import check_revision

async def check():
    engine = build_database_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(check_revision)
    finally:
        await engine.dispose()

run_database(check())
print('Read-only schema compatibility check passed.')
'''

VERIFY_STATE = (
    HTTP_CLIENT
    + '''
import base64

state = json.loads(sys.argv[1])
assert call('/ready')[0] == 200
assert call('/health')[0] == 200
path = '/api/v1/items/' + state['item']['id']
code, body = call(path)
assert code == 200 and json.loads(body) == state['item'], body
code, body = call('/api/v1/items', 'POST', state['body'], state['key'])
assert code == state['status'] and body == base64.b64decode(state['response']), body
code, body = call(path)
assert code == 200 and json.loads(body) == state['item'], body
code, body = call('/api/v1/items')
assert code == 200 and json.loads(body) == state['collection'], body
'''
)

ROLLBACK_WRITES = (
    VERIFY_STATE
    + '''
code, body = call(path, 'PATCH', {'name': 'Written during rollback', 'expected_version': 2})
assert code == 200, body
state['item'] = json.loads(body)
assert state['item']['version'] == 3
code, body = call('/api/v1/items', 'POST', {'name': 'Rollback-created item', 'price': 1.23})
assert code == 201, body
state['rollbackItem'] = json.loads(body)
code, body = call('/api/v1/items')
assert code == 200, body
state['collection'] = json.loads(body)
print(json.dumps(state))
'''
)

RECOVERY_WRITES = (
    VERIFY_STATE
    + '''
rollback_path = '/api/v1/items/' + state['rollbackItem']['id']
code, body = call(rollback_path)
assert code == 200 and json.loads(body) == state['rollbackItem'], body
code, body = call(path, 'PATCH', {'name': 'Recovered current image', 'expected_version': 3})
assert code == 200 and json.loads(body)['version'] == 4, body
assert call(path + '/delete', 'POST', {'expected_version': 4})[0] == 200
assert call(rollback_path + '/delete', 'POST', {'expected_version': 1})[0] == 200
assert call(path)[0] == 404 and call(rollback_path)[0] == 404
print('Retained state, cross-image replay and writes before/during/after rollback passed.')
'''
)


def validate_references(current: str, rollback: str, source: str) -> None:
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', source):
        raise ValueError('Expected the release source repository URL.')

    repository = (
        os.environ.get('REGISTRY', 'ghcr.io')
        + '/'
        + os.environ.get(
            'IMAGE_REPOSITORY', source.removeprefix('https://github.com/')
        ).lower()
    )

    for reference in (current, rollback):
        if not re.fullmatch(re.escape(repository) + r'@sha256:[a-f0-9]{64}', reference):
            raise ValueError(
                'Select immutable digests from this application release repository.'
            )

    if current == rollback:
        raise ValueError(
            'Rollback qualification requires two distinct retained images.'
        )


def qualify(current: str, rollback: str, source: str) -> None:
    output = ROOT / 'test-artifacts/rollback'

    output.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        'passed': False,
        'current': current,
        'rollback': rollback,
        'source': source,
    }

    write_json(output / 'result.json', record)

    def docker(
        *args: str, check: bool = True, env: dict[str, str] | None = None
    ) -> str:
        result = subprocess.run(
            ['docker', *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

        with (output / 'commands.log').open('a', encoding='utf-8') as log:
            log.write(f'{args!r}\n{result.stderr}\n')

            if result.returncode:
                log.write(result.stdout)

        if check and result.returncode:
            raise RuntimeError(
                f'Rollback command failed with exit {result.returncode}.'
            )

        return result.stdout.strip()

    # Do not touch a database until references, ownership and schema heads agree.
    try:
        validate_references(current, rollback, source)
        images: dict[str, dict[str, Any]] = {}

        for reference in (current, rollback):
            docker('pull', reference)

            data = mapping(
                sequence(json.loads(docker('image', 'inspect', reference)))[0]
            )
            image_config = mapping(data.get('Config'))
            labels = mapping(image_config.get('Labels'))
            version = str(labels.get('org.opencontainers.image.version', ''))
            revision = str(labels.get('org.opencontainers.image.revision', ''))

            if (
                reference not in sequence(data.get('RepoDigests'))
                or labels.get('org.opencontainers.image.source') != source
                or not SHA.fullmatch(revision)
                or not VERSION.fullmatch(version)
                or image_config.get('User') != '10001:10001'
            ):
                raise ValueError(
                    'Retained image identity, source, version or runtime user differs.'
                )

            heads = sequence(
                json.loads(
                    docker(
                        'run',
                        '--rm',
                        '--network',
                        'none',
                        '--read-only',
                        '--entrypoint',
                        'python',
                        reference,
                        '-c',
                        HEADS,
                    )
                )
            )

            if len(heads) != 1 or not isinstance(heads[0], str) or not heads[0]:
                raise ValueError('Each retained image must have one migration head.')

            images[reference] = {
                'version': version,
                'revision': revision,
                'head': heads[0],
            }

        record['images'] = images

        if images[current]['head'] != images[rollback]['head']:
            raise ValueError(
                'Image rollback requires exact schema-head equality; no database downgrade was attempted.'
            )

        if images[current]['revision'] == images[rollback]['revision']:
            raise ValueError(
                'Select releases from distinct source commits, not a same-source rebuild.'
            )
    except Exception as error:
        record['error'] = str(error)

        write_json(output / 'result.json', record)

        raise

    config = load_test_config()
    env = {
        **os.environ,
        **config.values,
        'ROLLBACK_CURRENT_IMAGE': current,
        'ROLLBACK_ACTIVE_IMAGE': current,
        'ROLLBACK_APP_VERSION': images[current]['version'],
        'ROLLBACK_DATABASE_URL': config.url.set(
            host='mysql-rollback', port=3306
        ).render_as_string(hide_password=False),
    }
    command = [
        'compose',
        '--env-file',
        str(ROOT / '.env.test'),
        '-p',
        'quickapi-fastapi-rollback',
        '-f',
        str(ROOT / 'docker-compose.rollback.yml'),
    ]
    retained_logs: list[str] = []
    transitions: list[dict[str, str]] = []

    def compose(*args: str) -> str:
        return docker(*command, *args, env=env)

    def stop() -> str:
        compose('stop', '--timeout', '35', 'api')

        identifier = compose('ps', '-a', '-q', 'api')
        logs = compose('logs', '--no-color', '--tail', '100', 'api')

        retained_logs.append(logs)

        if (
            docker('inspect', '--format', '{{.State.ExitCode}}', identifier) != '0'
            or 'Application exited (code 0)' not in logs
        ):
            raise ValueError('API failed graceful shutdown during rollback exercise.')

        return identifier

    def start(reference: str, mysql_id: str) -> str:
        env['ROLLBACK_ACTIVE_IMAGE'] = reference
        env['ROLLBACK_APP_VERSION'] = images[reference]['version']

        compose(
            'run',
            '--rm',
            '--no-deps',
            '--entrypoint',
            'python',
            'api',
            '-c',
            CHECK_SCHEMA,
        )
        compose('up', '-d', '--wait', '--no-deps', '--force-recreate', 'api')

        identifier = compose('ps', '-q', 'api')

        if not identifier or identifier in {
            transition['container'] for transition in transitions
        }:
            raise ValueError('Image transition did not replace the API container.')

        if (
            compose('ps', '-q', 'mysql-rollback') != mysql_id
            or docker('inspect', '--format', '{{.Config.Image}}', identifier)
            != reference
        ):
            raise ValueError(
                'Image transition changed MySQL or selected the wrong image.'
            )

        transitions.append({'image': reference, 'container': identifier})
        # Historical images keep their reviewed contents (such as a curl probe).
        # This compatibility exercise does not grant fresh security approval.
        checks = RUNTIME_CHECKS if reference == current else RETAINED_IDENTITY

        compose('exec', '-T', 'api', 'python', '-c', checks)

        return identifier

    try:
        compose('up', '-d', '--wait', 'mysql-rollback')
        compose('run', '--rm', 'migrate')

        mysql_id = compose('ps', '-q', 'mysql-rollback')

        if not mysql_id:
            raise ValueError('Missing disposable MySQL identity.')

        start(current, mysql_id)

        state = compose('exec', '-T', 'api', 'python', '-c', RESTART_SEED)

        stop()
        start(rollback, mysql_id)

        state = compose('exec', '-T', 'api', 'python', '-c', ROLLBACK_WRITES, state)

        stop()
        start(current, mysql_id)
        compose('exec', '-T', 'api', 'python', '-c', RECOVERY_WRITES, state)
        stop()

        record.update(mysqlContainer=mysql_id, transitions=transitions)
    except Exception as error:
        record['error'] = str(error)

        raise
    finally:
        try:
            retained_logs.append(
                docker(
                    *command,
                    'logs',
                    '--no-color',
                    '--tail',
                    '100',
                    env=env,
                    check=False,
                )
            )
            (output / 'mysql-api.log').write_text(
                '\n'.join(retained_logs), encoding='utf-8'
            )
        finally:
            try:
                compose('down', '--volumes', '--remove-orphans')
            except Exception as error:
                record['cleanupError'] = str(error)

                raise
            finally:
                write_json(output / 'result.json', record)

    record['passed'] = True

    write_json(output / 'result.json', record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--current-image', required=True)
    parser.add_argument('--rollback-image', required=True)
    parser.add_argument('--source', required=True)

    args = parser.parse_args()

    with command_lock():
        qualify(args.current_image, args.rollback_image, args.source)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
