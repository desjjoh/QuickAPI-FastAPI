"""Qualify a built runtime image against independent disposable MySQL."""

import argparse
import os
import subprocess
import sys

from scripts.test_database_support import ROOT, command_lock, load_test_config

RUNTIME_CHECKS = '''
import importlib.metadata
import os
from pathlib import Path
import shutil
import sys

assert os.getuid() == 10001 and os.getgid() == 10001, 'Unexpected runtime identity'
assert sys.prefix == '/opt/venv', 'Runtime dependencies must use /opt/venv'
installed = {distribution.metadata['Name'].lower().replace('_', '-')
    for distribution in importlib.metadata.distributions()}
for name in ['black', 'ruff', 'mypy', 'pytest', 'pytest-cov', 'pytest-asyncio', 'coverage']:
    assert name not in installed, f'Development dependency in runtime: {name}'
for command in ['cc', 'gcc', 'g++', 'make']:
    assert shutil.which(command) is None, f'Build tool in runtime: {command}'
assert shutil.which('curl'), 'Compose readiness probes require curl'
for name in ['/app', '/app/app', '/opt/venv', '/opt/venv/lib']:
    path = Path(name)
    assert os.access(path, os.R_OK | os.X_OK), f'Inaccessible runtime directory: {name}'
    assert not os.access(path, os.W_OK), f'Writable runtime directory: {name}'
for name in ['/app/app/main.py', '/app/alembic.ini', '/app/app/database/migrations/env.py']:
    path = Path(name)
    assert os.access(path, os.R_OK), f'Unreadable runtime file: {name}'
    assert not os.access(path, os.W_OK), f'Writable runtime file: {name}'
assert not Path('/app/scripts').exists(), 'Development scripts in runtime'
assert not Path('/app/.env').exists(), 'Local environment in runtime'
print('Built-image non-root identity, permissions and runtime-only dependencies verified.')
'''

HTTP_CLIENT = '''
import json
import sys
import urllib.error
import urllib.request

def call(path, method='GET', body=None, key=None):
    headers = {} if body is None else {'Content-Type': 'application/json'}
    if key is not None:
        headers['Idempotency-Key'] = key
    request = urllib.request.Request('http://127.0.0.1:8000' + path,
        data=None if body is None else json.dumps(body).encode(), method=method,
        headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
'''

HTTP_CHECKS = (
    HTTP_CLIENT
    + '''
assert call('/ready')[0] == 200
assert call('/health')[0] == 200
assert call('/favicon.ico')[0] == 200
for path in ['/docs', '/redoc', '/openapi.json', '/metrics', '/info', '/system']:
    assert call(path)[0] == 404, path
code, data = call('/api/v1/items/', 'POST', {'name':'Smoke','price':12.34})
assert code == 201, data
identifier = json.loads(data)['id']
path = '/api/v1/items/' + identifier
assert json.loads(call(path)[1])['name'] == 'Smoke'
assert call('/api/v1/items/')[0] == 200
code, data = call(path, 'PATCH', {'name':'Updated','expected_version':1})
assert code == 200 and json.loads(data)['name'] == 'Updated'
code, data = call(path, 'PUT', {'name':'Replaced','description':None,'price':9.99,'expected_version':2})
assert code == 200 and json.loads(data)['name'] == 'Replaced'
assert call(path + '/delete', 'POST', {'expected_version':3})[0] == 200
assert call(path)[0] == 404
print('Built-image MySQL CRUD, probes, static asset and exposure checks passed.')
'''
)

RESTART_SEED = (
    HTTP_CLIENT
    + '''
import base64

body = {'name': 'Restart persistence', 'price': 12.34}
key = 'container-replacement-create'
code, response = call('/api/v1/items', 'POST', body, key)
assert code == 201, response
created = json.loads(response)
assert created['version'] == 1
path = '/api/v1/items/' + created['id']
code, updated = call(path, 'PATCH', {'name': 'Retained update', 'expected_version': 1})
assert code == 200, updated
item = json.loads(updated)
assert item['version'] == 2 and item['name'] == 'Retained update'
code, collection = call('/api/v1/items')
assert code == 200, collection
print(json.dumps({'body': body, 'key': key, 'status': 201,
    'response': base64.b64encode(response).decode('ascii'), 'item': item,
    'collection': json.loads(collection)}))
'''
)

RESTART_CHECKS = (
    HTTP_CLIENT
    + '''
import base64

state = json.loads(sys.argv[1])
assert call('/ready')[0] == 200
assert call('/health')[0] == 200
path = '/api/v1/items/' + state['item']['id']
code, response = call(path)
assert code == 200 and json.loads(response) == state['item'], response
code, response = call('/api/v1/items', 'POST', state['body'], state['key'])
assert code == state['status'], response
assert response == base64.b64decode(state['response']), 'Replay bytes changed after replacement'
code, response = call(path)
assert code == 200 and json.loads(response) == state['item'], response
code, collection = call('/api/v1/items')
assert code == 200 and json.loads(collection) == state['collection'], collection
code, response = call(path, 'PATCH', {'name': 'After restart', 'expected_version': 2})
assert code == 200, response
item = json.loads(response)
assert item['version'] == 3 and item['name'] == 'After restart', response
code, response = call(path + '/delete', 'POST', {'expected_version': 3})
assert code == 200, response
assert call(path)[0] == 404
print('Built-image replacement, MySQL persistence, exact replay and fresh writes verified.')
'''
)


def qualify(image: str, *, cleanup_only: bool = False) -> None:
    config = load_test_config()
    env = {
        **os.environ,
        **config.values,
        'SMOKE_IMAGE': image,
        'SMOKE_DATABASE_URL': config.url.set(
            host='mysql-smoke', port=3306
        ).render_as_string(hide_password=False),
    }
    command = [
        'docker',
        'compose',
        '--env-file',
        str(ROOT / '.env.test'),
        '-p',
        'quickapi-fastapi-smoke',
        '-f',
        str(ROOT / 'docker-compose.smoke.yml'),
    ]

    def compose(*arguments: str) -> str:
        result = subprocess.run(
            [*command, *arguments],
            env=env,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        return result.stdout

    if cleanup_only:
        compose('down', '--volumes', '--remove-orphans')

        return

    failure = ''
    retained_logs: list[str] = []

    def stop_api() -> str:
        compose('stop', '--timeout', '35', 'api')
        identifier = compose('ps', '-a', '-q', 'api').strip()
        result = subprocess.run(
            ['docker', 'inspect', '--format', '{{.State.ExitCode}}', identifier],
            check=True,
            capture_output=True,
            text=True,
        )
        logs = compose('logs', '--no-color', 'api')

        retained_logs.append(logs)

        if result.stdout.strip() != '0' or 'Application exited (code 0)' not in logs:
            raise RuntimeError('Built-image graceful shutdown failed.')

        print('Built-image Docker SIGTERM and exit zero verified.')

        return identifier

    def image_id(identifier: str) -> str:
        return subprocess.run(
            ['docker', 'inspect', '--format', '{{.Image}}', identifier],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    try:
        identity = subprocess.run(
            ['docker', 'image', 'inspect', '--format', '{{.Config.User}}', image],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if identity != '10001:10001':
            raise RuntimeError('Built image must declare USER 10001:10001.')

        compose('up', '-d', '--wait', 'mysql-smoke')
        compose('run', '--rm', 'migrate')
        compose('up', '-d', '--wait', 'api')
        print(compose('exec', '-T', 'api', 'python', '-c', RUNTIME_CHECKS))
        print(compose('exec', '-T', 'api', 'python', '-c', HTTP_CHECKS))
        print(compose('exec', '-T', 'api', 'python', '-m', 'pip', 'check'))
        state = compose('exec', '-T', 'api', 'python', '-c', RESTART_SEED).strip()
        mysql_identifier = compose('ps', '-q', 'mysql-smoke').strip()
        original = stop_api()
        original_image = image_id(original)

        compose('up', '-d', '--wait', '--no-deps', '--force-recreate', 'api')

        replacement = compose('ps', '-q', 'api').strip()

        if not original or not replacement or replacement == original:
            raise RuntimeError('API qualification requires a new container identity.')

        if image_id(replacement) != original_image:
            raise RuntimeError('API replacement must use the same built image.')

        if (
            not mysql_identifier
            or compose('ps', '-q', 'mysql-smoke').strip() != mysql_identifier
        ):
            raise RuntimeError(
                'API replacement must preserve the running MySQL container.'
            )

        print(compose('exec', '-T', 'api', 'python', '-c', RUNTIME_CHECKS))
        print(compose('exec', '-T', 'api', 'python', '-c', RESTART_CHECKS, state))
        stop_api()
    except subprocess.CalledProcessError as error:
        failure = (error.stdout or '') + (error.stderr or '')

        raise
    except Exception as error:
        failure = str(error)

        raise
    finally:
        try:
            logs = subprocess.run(
                [*command, 'logs', '--no-color', '--tail', '100'],
                env=env,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            artifacts = ROOT / 'test-artifacts'

            artifacts.mkdir(exist_ok=True)
            (artifacts / 'production-mysql.log').write_text(
                failure
                + '\n'
                + '\n'.join(retained_logs)
                + '\n'
                + logs.stdout
                + logs.stderr,
                encoding='utf-8',
            )
        finally:
            compose('down', '--volumes', '--remove-orphans')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--image', default='quickapi-fastapi:ci')
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Remove only the disposable smoke project.',
    )
    args = parser.parse_args()

    try:
        with command_lock():
            qualify(args.image, cleanup_only=args.cleanup)

        return 0
    except Exception:
        print(
            'Built-image MySQL qualification failed; see test-artifacts/production-mysql.log.',
            file=sys.stderr,
        )

        return 1


if __name__ == '__main__':
    sys.exit(main())
