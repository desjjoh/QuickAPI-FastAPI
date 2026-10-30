import copy
import hashlib
import io
import json
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts import security_policy as policy
from scripts import security_scan as scanner

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 30, tzinfo=UTC)
PRODUCTION = {'fastapi': '1.0'}
EMPTY: dict[str, Any] = {'version': 1, 'exceptions': []}
IMAGE_ID = 'sha256:' + hashlib.sha256(b'{}').hexdigest()


def report(severity: str | None = None, *, image: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        'Target': 'Python' if image else '/input/requirements.txt',
        'Class': 'lang-pkgs',
        'Type': 'python-pkg' if image else 'pip',
        'Packages': [{'Name': 'fastapi', 'Version': '1.0'}],
    }

    if severity:
        result['Vulnerabilities'] = [
            {
                'VulnerabilityID': 'CVE-TEST-1',
                'PkgName': 'fastapi',
                'InstalledVersion': '1.0',
                'Severity': severity,
            }
        ]

    value: dict[str, Any] = {
        'SchemaVersion': 2,
        'ArtifactType': 'container_image' if image else 'filesystem',
        'Results': [result],
    }

    if image:
        value['Metadata'] = {
            'ImageID': IMAGE_ID,
            'OS': {'Family': 'debian', 'Name': '12'},
        }

        value['Results'].append(
            {
                'Target': 'debian',
                'Class': 'os-pkgs',
                'Type': 'debian',
                'Packages': [{'Name': 'libc6', 'Version': '1'}],
            }
        )

    return value


def evaluate(value: Any, rules: Any = None, **kwargs: Any) -> dict[str, Any]:
    return policy.evaluate(
        value,
        EMPTY if rules is None else rules,
        expected=PRODUCTION,
        production=PRODUCTION,
        now=NOW,
        **kwargs,
    )


@pytest.mark.parametrize(
    'severity', [None, 'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
)
@pytest.mark.parametrize('image', [False, True])
def test_severity_policy(severity: str | None, image: bool) -> None:
    result = evaluate(
        report(severity, image=image), image_id=IMAGE_ID if image else None
    )

    assert result['allowed'] is (severity != 'CRITICAL')
    assert len(result['findings']) == (0 if severity is None else 1)


def test_development_only_critical_is_visible_and_nonblocking() -> None:
    value = report('CRITICAL')

    value['Results'][0]['Packages'].append({'Name': 'pytest', 'Version': '2.0'})
    value['Results'][0]['Vulnerabilities'][0].update(
        PkgName='pytest', InstalledVersion='2.0'
    )

    result = policy.evaluate(
        value,
        EMPTY,
        expected=PRODUCTION | {'pytest': '2.0'},
        production=PRODUCTION,
        now=NOW,
    )

    assert result['allowed']
    assert result['findings'][0]['developmentOnly']


def exception() -> dict[str, Any]:
    return {
        'vulnerabilityId': 'CVE-TEST-1',
        'packageName': 'fastapi',
        'installedVersion': '1.0',
        'packagePath': None,
        'target': '/input/requirements.txt',
        'type': 'pip',
        'owner': 'maintainer',
        'reason': 'Temporary reviewed mitigation',
        'review': 'issue/1',
        'expiresOn': '2026-11-10',
    }


def test_exception_is_exact_and_finding_remains_visible() -> None:
    rule = exception()
    rules: dict[str, Any] = {'version': 1, 'exceptions': [rule]}

    result = evaluate(report('CRITICAL'), rules)

    assert result['allowed'] and result['findings'][0]['exception']

    for field in policy.SCOPE:
        changed = copy.deepcopy(rules)
        changed['exceptions'][0][field] = 'other'

        assert not evaluate(report('CRITICAL'), changed)['allowed']


@pytest.mark.parametrize(
    'change',
    [
        {'expiresOn': '2026-10-30'},
        {'expiresOn': '2026-12-01'},
        {'expiresOn': '2026-11-31'},
        {'owner': ''},
        {'packageName': '*'},
        {'packagePath': '?'},
        {'extra': 'unsupported'},
    ],
)
def test_invalid_exception_blocks_even_clean_report(change: dict[str, str]) -> None:
    rule = exception() | change

    with pytest.raises(ValueError):
        evaluate(report(), {'version': 1, 'exceptions': [rule]})


def test_duplicate_exception_fails() -> None:
    with pytest.raises(ValueError, match='Duplicate'):
        evaluate(report(), {'version': 1, 'exceptions': [exception(), exception()]})


@pytest.mark.parametrize(
    'failure',
    ['schema', 'results', 'inventory', 'version', 'severity', 'vulnerability'],
)
def test_incomplete_or_invalid_dependency_reports_block(failure: str) -> None:
    value = report('CRITICAL')
    result = value['Results'][0]

    if failure == 'schema':
        value['SchemaVersion'] = 1
    elif failure == 'results':
        value['Results'] = []
    elif failure == 'inventory':
        result.pop('Packages')
    elif failure == 'version':
        result['Packages'][0]['Version'] = 'different'
    elif failure == 'severity':
        result['Vulnerabilities'][0]['Severity'] = 'INVALID'
    else:
        result['Vulnerabilities'] = {}

    with pytest.raises(ValueError):
        evaluate(value)


@pytest.mark.parametrize('failure', ['identity', 'os', 'eol', 'python'])
def test_image_evidence_requires_identity_and_both_inventories(failure: str) -> None:
    value = report(image=True)

    if failure == 'identity':
        value['Metadata']['ImageID'] = 'sha256:other'
    elif failure == 'eol':
        value['Metadata']['OS']['EOSL'] = True
    elif failure == 'os':
        value['Results'].pop()
    else:
        value['Results'].pop(0)

    with pytest.raises(ValueError):
        evaluate(value, image_id=IMAGE_ID)


def write_archive(path: Path) -> None:
    with tarfile.open(path, 'w') as archive:
        for name, body in [
            ('manifest.json', b'[{"Config":"config.json"}]'),
            ('config.json', b'{}'),
        ]:
            member = tarfile.TarInfo(name)

            member.size = len(body)

            archive.addfile(member, io.BytesIO(body))


def test_exported_archive_identity_is_verified(tmp_path: Path) -> None:
    archive = tmp_path / 'image.tar'

    write_archive(archive)
    scanner.archive_identity(archive, IMAGE_ID)

    with pytest.raises(ValueError, match='configuration'):
        scanner.archive_identity(archive, 'sha256:' + '0' * 64)


@pytest.mark.parametrize('mode', ['dependencies', 'image'])
@pytest.mark.parametrize('failure', [False, True])
def test_scan_commands_and_fail_closed_evidence(
    mode: str, failure: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / 'requirements.txt').write_text('fastapi==1.0\n')
    (tmp_path / 'requirements-dev.txt').write_text('-r requirements.txt\npytest==2.0\n')
    (tmp_path / 'security').mkdir()

    for name in ('dependency-audit', 'container-vulnerability'):
        (tmp_path / 'security' / f'{name}-exceptions.json').write_text(
            json.dumps(EMPTY)
        )

    calls: list[list[str]] = []

    def run(arguments: list[str], _: Path) -> str:
        calls.append(arguments)

        if failure and (
            'filesystem' in arguments
            or ('image' in arguments and '--input' in arguments)
        ):
            raise RuntimeError('Injected scanner failure')

        if 'save' in arguments:
            write_archive(Path(arguments[arguments.index('--output') + 1]))

        if 'inspect' in arguments:
            return 'sha256:' + '1' * 64

        if '--input' in arguments:
            return json.dumps(report(image=True))

        if 'filesystem' in arguments:
            value = report()

            if any(
                'full:/input' in argument or 'full\\:/input' in argument
                for argument in arguments
            ):
                value['Results'][0]['Packages'].append(
                    {'Name': 'pytest', 'Version': '2.0'}
                )

            return json.dumps(value)

        return 'Trivy version test'

    monkeypatch.setattr(scanner, 'ROOT', tmp_path)
    monkeypatch.setattr(scanner, 'run', run)

    if failure:
        with pytest.raises(RuntimeError, match='Injected'):
            scanner.scan(mode, IMAGE_ID if mode == 'image' else None)
    else:
        assert scanner.scan(mode, IMAGE_ID if mode == 'image' else None)

    output = tmp_path / 'test-artifacts/security' / mode

    assert policy.read_json(output / 'result.json')['allowed'] is (not failure)
    assert (output / 'summary.md').exists()
    assert not list(output.glob('security-*'))
    assert not any(
        'docker.sock' in argument or argument == '--ignore-unfixed'
        for call in calls
        for argument in call
    )


def test_failed_tool_cannot_supply_usable_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments, 1, stdout=json.dumps(report()), stderr='Unavailable'
        )

    monkeypatch.setattr(
        scanner.subprocess,
        'run',
        failed,
    )

    with pytest.raises(RuntimeError, match='exit 1'):
        scanner.run(['scanner'], tmp_path)


@pytest.mark.parametrize('source', ['{"a":1,"a":2}', '{"value":NaN}', 'not-json'])
def test_invalid_json_evidence_is_rejected(source: str, tmp_path: Path) -> None:
    path = tmp_path / 'report.json'

    path.write_text(source, encoding='utf-8')

    with pytest.raises(ValueError):
        policy.read_json(path)


@pytest.mark.parametrize(
    'source', ['fastapi>=1.0', 'fastapi==1.*', '', 'fastapi==1.0\nFastAPI==2.0']
)
def test_invalid_requirements_cannot_omit_dependency_scope(
    source: str, tmp_path: Path
) -> None:
    path = tmp_path / 'requirements.txt'

    path.write_text(source, encoding='utf-8')

    with pytest.raises(ValueError):
        policy.requirements(path)
