"""Publish the verified OCI archive without rebuilding or dropping attestations."""

import argparse
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.release_candidate import context, run, verify
from scripts.release_oci import DIGEST, inspect
from scripts.security_policy import mapping, read_json
from scripts.security_scan import write_json


def publish(
    archive: Path,
    evidence: Path,
    image: str,
    *,
    sandbox: bool = False,
    docker_config: Path | None = None,
) -> dict[str, Any]:
    record = verify(archive, evidence)
    source, version, packages = context(evidence)

    if not re.fullmatch(r'[a-z0-9][a-z0-9.:-]*/[a-z0-9]+(?:[._/-][a-z0-9]+)*', image):
        raise ValueError('Invalid publication repository.')

    if not sandbox:
        rehearsal = mapping(read_json(evidence / 'registry-test.json'))

        if (
            image != source['image']
            or rehearsal.get('passed') is not True
            or rehearsal.get('digest') != record['digest']
            or rehearsal.get('archiveSha256') != record['archiveSha256']
        ):
            raise ValueError(
                'Publication requires matching source and registry rehearsal.'
            )

    config = (
        docker_config
        or Path(os.environ.get('DOCKER_CONFIG', str(Path.home() / '.docker')))
        / 'config.json'
    )

    if not config.is_file():
        raise ValueError('Registry login configuration is missing.')

    credentials = mapping(read_json(config))

    if credentials.get('credsStore') or credentials.get('credHelpers'):
        raise ValueError(
            'Publisher requires self-contained Docker login configuration.'
        )

    helper = os.environ.get('REGCTL_IMAGE', 'ghcr.io/regclient/regctl:latest')

    run(['docker', 'pull', helper], evidence)

    helper_id = run(
        ['docker', 'image', 'inspect', '--format', '{{.Id}}', helper], evidence
    ).strip()

    if not DIGEST.fullmatch(helper_id):
        raise ValueError('Invalid immutable publisher identity.')

    base = [
        'docker',
        'run',
        '--rm',
        '--user',
        f'{getattr(os, "getuid", lambda: 0)()}:{getattr(os, "getgid", lambda: 0)()}',
        '--env',
        'HOME=/publisher',
        '--network',
        'host',
        '--volume',
        f'{config.resolve()}:/publisher/.docker/config.json:ro',
        '--volume',
        f'{archive.parent.resolve()}:/candidate:ro',
    ]
    options: list[str] = []

    if sandbox:
        host = image.split('/', 1)[0]

        if not re.fullmatch(r'127\.0\.0\.1:[0-9]+', host):
            raise ValueError(
                'Plain HTTP rehearsal is restricted to the disposable loopback registry.'
            )

        options = ['--host', f'reg={host},tls=disabled']

    tags = [f'{image}:{source["sha"]}', f'{image}:{version}']

    run(
        [
            *base,
            helper_id,
            *options,
            'image',
            'import',
            tags[0],
            f'/candidate/{archive.name}',
        ],
        evidence,
    )

    for index, tag in enumerate(tags):
        if index:
            run(
                [
                    *base,
                    helper_id,
                    *options,
                    'image',
                    'copy',
                    f'{image}@{record["digest"]}',
                    tag,
                ],
                evidence,
            )

        if (
            run([*base, helper_id, *options, 'image', 'digest', tag], evidence).strip()
            != record['digest']
        ):
            raise ValueError(
                'Registry tag differs from the qualified candidate digest.'
            )

    with TemporaryDirectory(prefix='publication-', dir=archive.parent) as directory:
        returned = Path(directory) / 'image.tar'

        run(
            [
                *base,
                '--volume',
                f'{Path(directory).resolve()}:/roundtrip',
                helper_id,
                *options,
                'image',
                'copy',
                f'{image}@{record["digest"]}',
                'ocidir:///roundtrip/layout:verified',
            ],
            evidence,
        )

        layout = Path(directory) / 'layout'

        with tarfile.open(returned, 'w') as output:
            for file in sorted(layout.rglob('*')):
                if file.is_symlink():
                    raise ValueError('Registry export contains an unexpected link.')

                if file.is_file():
                    output.add(
                        file,
                        arcname=file.relative_to(layout).as_posix(),
                        recursive=False,
                    )

        roundtrip = inspect(returned, source, version, packages)

        if any(
            roundtrip[field] != record[field]
            for field in ('digest', 'runtimeDigest', 'imageId')
        ):
            raise ValueError(
                'Registry round-trip changed candidate or attestation identity.'
            )

    # Recheck local archive/evidence/policy immediately before recording publication.
    verify(archive, evidence)

    publication = {
        'image': image,
        'digest': record['digest'],
        'tags': tags,
        'archiveSha256': record['archiveSha256'],
        'source': source,
        'publisherImageId': helper_id,
        'publishedAt': time.time(),
        'passed': True,
    }

    write_json(
        evidence / ('registry-test.json' if sandbox else 'publication.json'),
        publication,
    )

    if not sandbox:
        reference = f'{image}@{record["digest"]}'

        (evidence / 'release-image.env').write_text(
            f'QUICKAPI_IMAGE={reference}\n', encoding='utf-8'
        )

        if os.environ.get('GITHUB_OUTPUT'):
            with Path(os.environ['GITHUB_OUTPUT']).open(
                'a', encoding='utf-8'
            ) as output:
                output.write(f'quickapi-image={reference}\n')

    return publication


def registry_test(archive: Path, evidence: Path) -> None:
    verify(archive, evidence)

    name = 'quickapi-release-' + uuid.uuid4().hex
    image = 'registry:3'

    run(['docker', 'pull', image], evidence)

    registry_id = run(
        ['docker', 'image', 'inspect', '--format', '{{.Id}}', image], evidence
    ).strip()

    if not DIGEST.fullmatch(registry_id):
        raise ValueError('Invalid registry test image identity.')

    try:
        run(
            [
                'docker',
                'run',
                '-d',
                '--name',
                name,
                '--publish',
                '127.0.0.1::5000',
                '--tmpfs',
                '/var/lib/registry',
                registry_id,
            ],
            evidence,
        )

        address = run(['docker', 'port', name, '5000/tcp'], evidence).strip()

        if not re.fullmatch(r'127\.0\.0\.1:[0-9]+', address):
            raise ValueError('Disposable registry must publish only to loopback.')

        for attempt in range(30):
            try:
                with urllib.request.urlopen(
                    f'http://{address}/v2/', timeout=1
                ) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                pass

            if attempt == 29:
                raise RuntimeError('Disposable registry did not become ready.')

            time.sleep(0.2)

        with TemporaryDirectory(
            prefix='registry-auth-', dir=archive.parent
        ) as directory:
            config = Path(directory) / 'config.json'

            config.write_text(json.dumps({'auths': {}}), encoding='utf-8')
            publish(
                archive,
                evidence,
                address + '/quickapi/rehearsal',
                sandbox=True,
                docker_config=config,
            )
    finally:
        run(['docker', 'rm', '--force', '--volumes', name], evidence)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('mode', choices=['registry-test', 'publish'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('evidence', type=Path)

    args = parser.parse_args()

    try:
        if args.mode == 'registry-test':
            registry_test(args.archive.resolve(), args.evidence.resolve())
        else:
            (args.evidence / 'release-image.env').unlink(missing_ok=True)
            (args.evidence / 'publication.json').unlink(missing_ok=True)
            publish(
                args.archive.resolve(),
                args.evidence.resolve(),
                os.environ['RELEASE_IMAGE'],
            )

        return 0
    except Exception as error:
        write_json(
            args.evidence / 'failure.json', {'stage': args.mode, 'error': str(error)}
        )
        print(f'Release publication blocked: {error}', file=sys.stderr)

        return 1


if __name__ == '__main__':
    sys.exit(main())
