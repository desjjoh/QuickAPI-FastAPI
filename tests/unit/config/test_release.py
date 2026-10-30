import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from scripts import release_candidate as candidate
from scripts import release_oci as oci
from scripts import release_publish as publisher
from scripts import release_source as source_tool
from scripts.security_scan import write_json

pytestmark = pytest.mark.unit
SOURCE: dict[str, Any] = {
    'sha': 'a' * 40,
    'repository': 'https://github.com/example/app',
    'image': 'ghcr.io/example/app',
    'ciRunId': 42,
    'ciAttempt': 1,
}
VERSION = '1.3.0'
PACKAGES = {'fastapi': '1.0'}


def make_archive(path: Path, failure: str = '') -> dict[str, Any]:
    files: dict[str, bytes] = {}

    def blob(
        value: Any, media: str = 'application/vnd.oci.image.manifest.v1+json'
    ) -> dict[str, Any]:
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        digest = hashlib.sha256(body).hexdigest()

        files['blobs/sha256/' + digest] = body

        return {'digest': 'sha256:' + digest, 'size': len(body), 'mediaType': media}

    labels = {
        'org.opencontainers.image.revision': SOURCE['sha'],
        'org.opencontainers.image.source': SOURCE['repository'],
        'org.opencontainers.image.version': VERSION,
    }

    if failure == 'labels':
        labels['org.opencontainers.image.revision'] = 'b' * 40

    config = blob(
        {'architecture': 'amd64', 'os': 'linux', 'config': {'Labels': labels}},
        'application/vnd.oci.image.config.v1+json',
    )
    layer = blob(
        b'compressed layer bytes', 'application/vnd.oci.image.layer.v1.tar+gzip'
    )
    runtime = blob({'schemaVersion': 2, 'config': config, 'layers': [layer]})
    runtime['platform'] = {'architecture': 'amd64', 'os': 'linux'}
    sbom: dict[str, Any] = {
        'spdxVersion': 'SPDX-2.3',
        'packages': [{'name': 'fastapi', 'versionInfo': '1.0'}],
    }
    provenance: dict[str, Any] = {
        'buildDefinition': {
            'resolvedDependencies': [
                {
                    'uri': 'git+' + SOURCE['repository'] + '.git#refs/heads/main',
                    'digest': {
                        'sha1': SOURCE['sha'] if failure != 'provenance' else 'b' * 40
                    },
                }
            ]
        }
    }

    if failure == 'sbom_inventory':
        sbom['packages'] = []

    statements: list[dict[str, Any]] = []

    for kind, predicate in [
        ('https://spdx.dev/Document', sbom),
        ('https://slsa.dev/provenance/v1', provenance),
    ]:
        if failure == 'missing_sbom' and 'spdx' in kind:
            continue

        statement = blob(
            {
                '_type': 'https://in-toto.io/Statement/v1',
                'subject': [
                    {
                        'name': 'runtime',
                        'digest': {
                            'sha256': (
                                runtime['digest'][7:]
                                if failure != 'subject'
                                else '0' * 64
                            )
                        },
                    }
                ],
                'predicateType': kind,
                'predicate': predicate,
            },
            'application/vnd.in-toto+json',
        )
        statement['annotations'] = {'in-toto.io/predicate-type': kind}

        statements.append(statement)

    attestation_body: dict[str, Any] = {
        'schemaVersion': 2,
        'config': blob({}),
        'layers': statements,
    }

    if failure in {'artifact_storage', 'inline_artifact', 'conflicting_binding'}:
        attestation_body.update(
            artifactType='application/vnd.docker.attestation.manifest.v1+json',
            subject=runtime
            | (
                {'digest': 'sha256:' + '0' * 64}
                if failure == 'conflicting_binding'
                else {}
            ),
        )

    if failure == 'inline_artifact':
        inline = attestation_body['config']
        inline['data'] = 'e30='

        files.pop('blobs/sha256/' + inline['digest'][7:])

    attestation = blob(attestation_body)

    attestation.update(
        platform={'architecture': 'unknown', 'os': 'unknown'},
        annotations={
            'vnd.docker.reference.type': 'attestation-manifest',
            'vnd.docker.reference.digest': (
                runtime['digest'] if failure != 'binding' else 'sha256:' + '0' * 64
            ),
        },
    )
    if failure in {'artifact_storage', 'inline_artifact'}:
        attestation.pop('annotations')

    entries = [runtime, attestation]

    if failure == 'ambiguous_runtime':
        entries.append(runtime)

    index = blob(
        {'schemaVersion': 2, 'manifests': entries},
        'application/vnd.oci.image.index.v1+json',
    )
    roots = [index]

    if failure in {'registry_catalog', 'digest_aliases', 'conflicting_alias'}:
        roots.insert(
            0,
            blob(
                {'schemaVersion': 2, 'manifests': []},
                'application/vnd.oci.image.index.v1+json',
            ),
        )

    if failure in {'digest_aliases', 'conflicting_alias'}:
        alias: dict[str, Any] = index | {
            'annotations': {'org.opencontainers.image.ref.name': 'verified'}
        }

        if failure == 'conflicting_alias':
            alias['size'] += 1

        roots.append(alias)

    files['index.json'] = json.dumps({'schemaVersion': 2, 'manifests': roots}).encode()
    files['oci-layout'] = b'{"imageLayoutVersion":"1.0.0"}'

    if failure == 'blob':
        files['blobs/sha256/' + layer['digest'][7:]] = b'X' * layer['size']
    elif failure == 'unsafe':
        files['../outside'] = b'unsafe'

    with tarfile.open(path, 'w') as archive:
        for name, body in files.items():
            member = tarfile.TarInfo(name)

            member.size = len(body)

            archive.addfile(member, io.BytesIO(body))

    return {
        'digest': index['digest'],
        'runtimeDigest': runtime['digest'],
        'imageId': config['digest'],
    }


@pytest.mark.parametrize(
    'failure',
    [
        'labels',
        'provenance',
        'sbom_inventory',
        'missing_sbom',
        'subject',
        'binding',
        'conflicting_binding',
        'ambiguous_runtime',
        'blob',
        'unsafe',
    ],
)
def test_candidate_rejects_wrong_source_attestations_or_content(
    tmp_path: Path, failure: str
) -> None:
    archive = tmp_path / 'image.tar'

    make_archive(archive, failure)

    with pytest.raises(ValueError):
        oci.inspect(archive, SOURCE, VERSION, PACKAGES)


def test_valid_candidate_preserves_root_runtime_and_attestations(
    tmp_path: Path,
) -> None:
    archive = tmp_path / 'image.tar'
    identity = make_archive(archive)
    info = oci.inspect(archive, SOURCE, VERSION, PACKAGES)

    assert all(info[field] == value for field, value in identity.items())
    assert info['sbom']['packages'][0]['name'] == 'fastapi'
    assert info['provenance']['buildDefinition']['resolvedDependencies']


@pytest.mark.parametrize('mode', ['registry_catalog', 'digest_aliases'])
def test_registry_layout_selects_only_the_approved_digest(
    tmp_path: Path, mode: str
) -> None:
    archive = tmp_path / 'image.tar'
    identity = make_archive(archive, mode)

    assert (
        oci.inspect(
            archive, SOURCE, VERSION, PACKAGES, expected_digest=identity['digest']
        )['digest']
        == identity['digest']
    )

    with pytest.raises(ValueError, match='exactly one'):
        oci.inspect(archive, SOURCE, VERSION, PACKAGES)

    with pytest.raises(ValueError, match='missing'):
        oci.inspect(
            archive, SOURCE, VERSION, PACKAGES, expected_digest='sha256:' + '0' * 64
        )


def test_registry_layout_rejects_conflicting_approved_descriptors(
    tmp_path: Path,
) -> None:
    archive = tmp_path / 'image.tar'
    identity = make_archive(archive, 'conflicting_alias')

    with pytest.raises(ValueError, match='Conflicting'):
        oci.inspect(
            archive, SOURCE, VERSION, PACKAGES, expected_digest=identity['digest']
        )


@pytest.mark.parametrize('mode', ['artifact_storage', 'inline_artifact'])
def test_oci_artifact_subject_storage_is_supported(tmp_path: Path, mode: str) -> None:
    archive = tmp_path / 'image.tar'
    identity = make_archive(archive, mode)

    assert (
        oci.inspect(archive, SOURCE, VERSION, PACKAGES)['digest'] == identity['digest']
    )


@pytest.fixture
def release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, Any]]:
    (tmp_path / 'requirements.txt').write_text('fastapi==1.0\n')
    (tmp_path / 'VERSION').write_text(VERSION)
    (tmp_path / '.env.example').write_text('APP_VERSION=' + VERSION)
    (tmp_path / 'security').mkdir()

    write_json(
        tmp_path / 'security/container-vulnerability-exceptions.json',
        {'version': 1, 'exceptions': []},
    )

    evidence = tmp_path / 'evidence'

    evidence.mkdir()
    write_json(evidence / 'source.json', SOURCE)

    archive = tmp_path / 'image.tar'
    identity = make_archive(archive)

    monkeypatch.setattr(candidate, 'ROOT', tmp_path)
    monkeypatch.setenv('RELEASE_SHA', SOURCE['sha'])
    monkeypatch.setenv('RELEASE_SOURCE', SOURCE['repository'])
    monkeypatch.setenv('BUILD_DIGEST', identity['digest'])

    def run(arguments: list[str], _: Path) -> str:
        if 'inspect' in arguments:
            return (
                'sha256:' + '1' * 64
                if 'aquasec' in arguments[-1]
                else identity['imageId']
            )

        if '--input' in arguments and '/image' in arguments:
            return json.dumps(
                {
                    'SchemaVersion': 2,
                    'ArtifactType': 'container_image',
                    'Metadata': {
                        'ImageID': identity['imageId'],
                        'OS': {'Family': 'debian', 'Name': '13'},
                    },
                    'Results': [
                        {
                            'Target': 'Python',
                            'Class': 'lang-pkgs',
                            'Type': 'python-pkg',
                            'Packages': [{'Name': 'fastapi', 'Version': '1.0'}],
                        },
                        {
                            'Target': 'debian',
                            'Class': 'os-pkgs',
                            'Type': 'debian',
                            'Packages': [{'Name': 'libc6', 'Version': '2.41'}],
                        },
                    ],
                }
            )

        return 'successful tool output'

    monkeypatch.setattr(candidate, 'run', run)

    candidate.qualify(archive, evidence)

    return archive, evidence, identity


def test_qualification_and_verification_use_exact_candidate(
    release: tuple[Path, Path, dict[str, Any]],
) -> None:
    archive, evidence, identity = release
    record = candidate.verify(archive, evidence)

    assert record['digest'] == identity['digest']
    assert json.loads((evidence / 'smoke.json').read_text())['passed'] is True

    with pytest.raises(ValueError, match='fresh'):
        candidate.qualify(archive, evidence)


@pytest.mark.parametrize(
    'name',
    [
        'source.json',
        'smoke.json',
        'smoke.log',
        'vulnerabilities.json',
        'gate.json',
        'sbom.spdx.json',
        'provenance.json',
    ],
)
def test_changed_evidence_blocks_publication(
    release: tuple[Path, Path, dict[str, Any]], name: str
) -> None:
    archive, evidence, _ = release

    with (evidence / name).open('a') as output:
        output.write('\n')

    with pytest.raises(ValueError, match='changed'):
        candidate.verify(archive, evidence)


@pytest.mark.parametrize(
    'failure', ['archive', 'failure_marker', 'policy', 'stale', 'build_digest']
)
def test_invalid_release_cannot_publish(
    release: tuple[Path, Path, dict[str, Any]],
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, evidence, _ = release

    if failure == 'archive':
        with archive.open('ab') as output:
            output.write(b'changed')
    elif failure == 'failure_marker':
        write_json(evidence / 'failure.json', {'failed': True})
    elif failure == 'policy':
        with (candidate.ROOT / 'security/container-vulnerability-exceptions.json').open(
            'a'
        ) as output:
            output.write('\n')
    elif failure == 'build_digest':
        monkeypatch.setenv('BUILD_DIGEST', 'sha256:' + '0' * 64)
    else:
        record = json.loads((evidence / 'candidate.json').read_text())
        record['scannedAt'] = (datetime.now(UTC) - timedelta(days=2)).isoformat()

        write_json(evidence / 'candidate.json', record)

    with pytest.raises(ValueError):
        candidate.verify(archive, evidence)


def test_source_selection_requires_successful_exact_main_push() -> None:
    run: dict[str, Any] = {
        'head_sha': SOURCE['sha'],
        'head_branch': 'main',
        'event': 'push',
        'status': 'completed',
        'conclusion': 'success',
        'name': 'Quality',
        'head_repository': {'full_name': 'example/app'},
    }
    jobs: list[Any] = [
        {'name': 'Deployment gate', 'status': 'completed', 'conclusion': 'success'}
    ]

    source_tool.validate_ci(run, jobs, SOURCE['sha'], 'example/app')

    for field, value in [
        ('event', 'pull_request'),
        ('head_branch', 'dev'),
        ('head_sha', 'b' * 40),
        ('status', 'in_progress'),
        ('conclusion', 'failure'),
    ]:
        with pytest.raises(ValueError):
            source_tool.validate_ci(
                run | {field: value}, jobs, SOURCE['sha'], 'example/app'
            )

    for status in ('failure', 'cancelled', 'skipped'):
        with pytest.raises(ValueError):
            source_tool.validate_ci(
                run, [jobs[0] | {'conclusion': status}], SOURCE['sha'], 'example/app'
            )


def test_source_selection_uses_latest_attempt_and_main_ancestry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('REQUESTED_SHA', SOURCE['sha'])
    monkeypatch.setenv('GITHUB_REPOSITORY', 'example/app')

    def api(path: str) -> dict[str, Any]:
        if 'compare' in path:
            return {'status': 'ahead', 'merge_base_commit': {'sha': SOURCE['sha']}}

        if 'workflow' in path:
            return {
                'workflow_runs': [
                    {
                        'id': 42,
                        'run_attempt': 2,
                        'head_sha': SOURCE['sha'],
                        'head_branch': 'main',
                        'event': 'push',
                        'status': 'completed',
                        'conclusion': 'success',
                        'name': 'Quality',
                        'head_repository': {'full_name': 'example/app'},
                    }
                ]
            }

        assert '/attempts/2/jobs?' in path

        return {
            'jobs': [
                {
                    'name': 'Deployment gate',
                    'status': 'completed',
                    'conclusion': 'success',
                }
            ]
        }

    monkeypatch.setattr(source_tool, 'api', api)

    assert source_tool.select_source()['ciAttempt'] == 2


@pytest.mark.parametrize('mismatch', [False, True])
def test_publication_preserves_digest_and_requires_no_rebuild(
    release: tuple[Path, Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    mismatch: bool,
) -> None:
    archive, evidence, identity = release
    config = evidence / 'docker-config.json'

    write_json(config, {'auths': {}})

    calls: list[list[str]] = []

    def run(arguments: list[str], _: Path) -> str:
        calls.append(arguments)

        if 'inspect' in arguments:
            return 'sha256:' + '2' * 64

        if 'digest' in arguments:
            return 'sha256:' + '0' * 64 if mismatch else identity['digest']

        if any(argument.startswith('ocidir:') for argument in arguments):
            mount = next(
                argument for argument in arguments if argument.endswith(':/roundtrip')
            )
            directory = Path(mount.removesuffix(':/roundtrip')) / 'layout'
            content = oci.Candidate(archive)

            try:
                content.extract(directory)
            finally:
                content.close()

            # Reproduce regctl layouts that catalog more than the requested root.
            index_path = directory / 'index.json'
            index = json.loads(index_path.read_text())

            index['manifests'].append(
                index['manifests'][0]
                | {
                    'annotations': {'org.opencontainers.image.ref.name': 'verified'},
                }
            )

            write_json(index_path, index)

        return ''

    monkeypatch.setattr(publisher, 'run', run)

    if mismatch:
        with pytest.raises(ValueError, match='digest'):
            publisher.publish(
                archive,
                evidence,
                '127.0.0.1:5000/rehearsal',
                sandbox=True,
                docker_config=config,
            )

        assert not (evidence / 'registry-test.json').exists()
    else:
        result = publisher.publish(
            archive,
            evidence,
            '127.0.0.1:5000/rehearsal',
            sandbox=True,
            docker_config=config,
        )

        assert result['digest'] == identity['digest']
        assert (evidence / 'registry-test.json').exists()
        assert not (evidence / 'release-image.env').exists()

        before_publication = len(calls)

        publisher.publish(archive, evidence, SOURCE['image'], docker_config=config)

        assert (
            evidence / 'release-image.env'
        ).read_text().strip() == f'QUICKAPI_IMAGE={SOURCE["image"]}@{identity["digest"]}'
        assert not any('--host' in call for call in calls[before_publication:])

    assert not any('build' in call for call in calls)
    assert not any('docker.sock' in argument for call in calls for argument in call)


def test_real_publication_requires_rehearsal(
    release: tuple[Path, Path, dict[str, Any]],
) -> None:
    archive, evidence, _ = release

    with pytest.raises(FileNotFoundError):
        publisher.publish(archive, evidence, SOURCE['image'])


def test_disposable_registry_is_removed_when_publication_fails(
    release: tuple[Path, Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, evidence, _ = release
    calls: list[list[str]] = []

    def run(arguments: list[str], _: Path) -> str:
        calls.append(arguments)

        if 'inspect' in arguments:
            return 'sha256:' + '3' * 64

        return '127.0.0.1:5000' if 'port' in arguments else ''

    def failed(*_: Any, **__: Any) -> dict[str, Any]:
        raise ValueError('Injected publication failure')

    response = MagicMock()
    response.__enter__.return_value.status = 200

    monkeypatch.setattr(publisher, 'run', run)
    monkeypatch.setattr(publisher, 'publish', failed)
    monkeypatch.setattr(
        publisher.urllib.request, 'urlopen', MagicMock(return_value=response)
    )

    with pytest.raises(ValueError, match='Injected'):
        publisher.registry_test(archive, evidence)

    assert calls[-1][:4] == ['docker', 'rm', '--force', '--volumes']
    assert calls[-1][-1].startswith('quickapi-release-')


def test_current_policy_blocks_critical_even_with_forged_passing_gate(
    release: tuple[Path, Path, dict[str, Any]],
) -> None:
    archive, evidence, _ = release
    report_path = evidence / 'vulnerabilities.json'
    report = json.loads(report_path.read_text())
    report['Results'][0]['Vulnerabilities'] = [
        {
            'VulnerabilityID': 'CVE-TEST',
            'PkgName': 'fastapi',
            'InstalledVersion': '1.0',
            'Severity': 'CRITICAL',
        }
    ]

    write_json(report_path, report)

    record = json.loads((evidence / 'candidate.json').read_text())
    record['files']['vulnerabilities.json'] = candidate.sha256(report_path)

    write_json(evidence / 'candidate.json', record)

    with pytest.raises(ValueError, match='Critical'):
        candidate.verify(archive, evidence)


def test_version_drift_blocks_release(
    release: tuple[Path, Path, dict[str, Any]],
) -> None:
    (candidate.ROOT / 'VERSION').write_text('1.4.0')

    with pytest.raises(ValueError, match='agree'):
        source_tool.release_version(candidate.ROOT)


def test_release_workflow_keeps_trust_dry_run_and_single_build_boundaries() -> None:
    root = Path(__file__).resolve().parents[3]
    document = yaml.load(
        (root / '.github/workflows/release-image.yml').read_text(),
        Loader=yaml.BaseLoader,
    )
    job = document['jobs']['release']
    steps = job['steps']
    builds = [
        step
        for step in steps
        if step.get('uses', '').startswith('docker/build-push-action@')
    ]

    assert len(builds) == 1
    assert builds[0]['with']['push'] == 'false'
    assert builds[0]['with']['sbom'] == 'true'
    assert builds[0]['with']['provenance'] == 'mode=max,version=v1'
    assert document['on']['workflow_dispatch']['inputs']['dry-run']['default'] == 'true'
    assert document['on']['workflow_run']['workflows'] == ['Quality']
    assert document['on']['workflow_run']['branches'] == ['main']
    assert 'head_repository.full_name == github.repository' in job['if']

    for step in steps:
        assert step.get('continue-on-error', 'false') == 'false'

        if (
            step.get('uses', '').startswith('docker/login-action@')
            or step.get('id') == 'publication'
        ):
            assert (
                step['if']
                == "github.event_name == 'workflow_run' || inputs.dry-run == false"
            )

    names = [step.get('name', '') for step in steps]

    assert names.index('Qualify the exact unpublished candidate') < names.index(
        'Log in only after candidate approval'
    )
    assert names.index(
        'Rehearse digest-preserving publication in a disposable registry'
    ) < names.index('Log in only after candidate approval')
    assert names.index('Recheck exact-source CI before registry login') < names.index(
        'Log in only after candidate approval'
    )
