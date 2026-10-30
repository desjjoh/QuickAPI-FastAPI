"""Qualify and verify one source-bound OCI release candidate."""

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.release_oci import DIGEST, Candidate, inspect
from scripts.release_source import SHA, release_version
from scripts.security_policy import evaluate, mapping, read_json, requirements
from scripts.security_scan import sha256, write_json

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str], evidence: Path) -> str:
    result = subprocess.run(
        arguments, cwd=ROOT, capture_output=True, text=True, timeout=600
    )

    with (evidence / 'commands.log').open('a', encoding='utf-8') as log:
        log.write(f'{arguments!r}\n{result.stderr}\n')

        if result.returncode:
            log.write(result.stdout)

    if result.returncode:
        raise RuntimeError(
            f'Release tool exited {result.returncode}; see commands.log.'
        )

    return result.stdout


def context(evidence: Path) -> tuple[dict[str, Any], str, dict[str, str]]:
    source = mapping(read_json(evidence / 'source.json'))

    if (
        not SHA.fullmatch(str(source.get('sha', '')))
        or source.get('sha') != os.environ.get('RELEASE_SHA')
        or source.get('repository') != os.environ.get('RELEASE_SOURCE')
    ):
        raise ValueError(
            'Release evidence must match the independently selected source.'
        )

    return source, release_version(ROOT), requirements(ROOT / 'requirements.txt')


def scan_archive(
    archive: Path, evidence: Path, info: dict[str, Any], packages: dict[str, str]
) -> dict[str, Any]:
    reference = os.environ.get('TRIVY_SCANNER_IMAGE', 'aquasec/trivy:latest')

    run(['docker', 'pull', reference], evidence)

    scanner = run(
        ['docker', 'image', 'inspect', '--format', '{{.Id}}', reference], evidence
    ).strip()

    if not DIGEST.fullmatch(scanner):
        raise ValueError('Invalid immutable scanner identity.')

    cache = ROOT / '.cache/trivy'

    cache.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix='release-layout-', dir=archive.parent) as directory:
        candidate = Candidate(archive)

        try:
            candidate.extract(Path(directory))
        finally:
            candidate.close()

        report = run(
            [
                'docker',
                'run',
                '--rm',
                '--volume',
                f'{Path(directory).resolve()}:/image:ro',
                '--volume',
                f'{cache.resolve()}:/root/.cache/trivy',
                scanner,
                'image',
                '--input',
                '/image',
                '--scanners',
                'vuln',
                '--list-all-pkgs',
                '--ignorefile',
                '/dev/null',
                '--format',
                'json',
                '--exit-code',
                '0',
                '--timeout',
                '5m',
            ],
            evidence,
        )

        (evidence / 'vulnerabilities.json').write_text(report, encoding='utf-8')

    decision = evaluate(
        read_json(evidence / 'vulnerabilities.json'),
        read_json(ROOT / 'security/container-vulnerability-exceptions.json'),
        expected=packages,
        production=packages,
        image_id=info['imageId'],
    )

    write_json(evidence / 'gate.json', decision)
    (evidence / 'summary.md').write_text(
        f'# Release security gate: {"PASS" if decision["allowed"] else "BLOCKED"}\n\n'
        f'Critical blockers: {len(decision["blocked"])}; findings: {len(decision["findings"])}.\n',
        encoding='utf-8',
    )

    for severity in ('CRITICAL', 'HIGH', 'MEDIUM'):
        count = sum(finding['severity'] == severity for finding in decision['findings'])

        if count:
            print(
                f'::warning::{count} {severity} release findings; see retained evidence.'
            )

    return {
        'scannerId': scanner,
        'scannerVersion': run(
            ['docker', 'run', '--rm', scanner, '--version'], evidence
        ),
        'scannedAt': datetime.now(UTC).isoformat(),
    }


def qualify(archive: Path, evidence: Path) -> None:
    if any(
        (evidence / name).exists()
        for name in ('candidate.json', 'smoke.json', 'gate.json', 'failure.json')
    ):
        raise ValueError('Release qualification requires fresh evidence.')

    source, version, packages = context(evidence)
    info = inspect(archive, source, version, packages)
    archive_hash = sha256(archive)

    if info['digest'] != os.environ.get('BUILD_DIGEST'):
        raise ValueError('Build output and candidate index digest differ.')

    identity = {
        'source': source,
        'version': version,
        'digest': info['digest'],
        'runtimeDigest': info['runtimeDigest'],
        'imageId': info['imageId'],
        'archiveSha256': archive_hash,
    }

    write_json(evidence / 'smoke.json', {**identity, 'passed': False})
    run(['docker', 'load', '--input', str(archive)], evidence)

    loaded = run(
        ['docker', 'image', 'inspect', '--format', '{{.Id}}', info['digest']], evidence
    ).strip()

    if loaded not in {info['digest'], info['imageId']}:
        raise ValueError('Loaded image differs from OCI candidate.')

    output = run(
        [sys.executable, '-m', 'scripts.test_image', '--image', loaded], evidence
    )

    (evidence / 'smoke.log').write_text(output, encoding='utf-8')
    write_json(evidence / 'smoke.json', {**identity, 'passed': True})

    scanner = scan_archive(archive, evidence, info, packages)

    if sha256(archive) != archive_hash:
        raise ValueError('Candidate archive changed during qualification.')

    write_json(evidence / 'sbom.spdx.json', info['sbom'])
    write_json(evidence / 'provenance.json', info['provenance'])

    files = (
        'source.json',
        'smoke.json',
        'smoke.log',
        'vulnerabilities.json',
        'gate.json',
        'sbom.spdx.json',
        'provenance.json',
    )

    write_json(
        evidence / 'candidate.json',
        {
            **identity,
            **scanner,
            'files': {name: sha256(evidence / name) for name in files},
            'policySha256': sha256(
                ROOT / 'security/container-vulnerability-exceptions.json'
            ),
        },
    )
    verify(archive, evidence)


def verify(archive: Path, evidence: Path) -> dict[str, Any]:
    if (evidence / 'failure.json').exists():
        raise ValueError('A failed release attempt cannot publish.')

    source, version, packages = context(evidence)
    info = inspect(archive, source, version, packages)
    record = mapping(read_json(evidence / 'candidate.json'))
    expected_files = {
        'source.json',
        'smoke.json',
        'smoke.log',
        'vulnerabilities.json',
        'gate.json',
        'sbom.spdx.json',
        'provenance.json',
    }

    if set(mapping(record.get('files'))) != expected_files:
        raise ValueError('Incomplete bound release evidence.')

    for name, digest in mapping(record['files']).items():
        if sha256(evidence / name) != digest:
            raise ValueError('Bound release evidence changed.')

    if (
        record.get('source') != source
        or record.get('version') != version
        or record.get('archiveSha256') != sha256(archive)
        or record.get('policySha256')
        != sha256(ROOT / 'security/container-vulnerability-exceptions.json')
    ):
        raise ValueError('Candidate source, archive, version or policy changed.')

    for field in ('digest', 'runtimeDigest', 'imageId'):
        if record.get(field) != info[field]:
            raise ValueError('Candidate identity differs from retained evidence.')

    if info['digest'] != os.environ.get('BUILD_DIGEST') or not DIGEST.fullmatch(
        str(record.get('scannerId', ''))
    ):
        raise ValueError('Missing build/scanner identity.')

    scanned = datetime.fromisoformat(record['scannedAt'])

    if scanned.tzinfo is None or not -timedelta(minutes=5) <= datetime.now(
        UTC
    ) - scanned <= timedelta(hours=24):
        raise ValueError('Release scan evidence is stale or has an invalid clock.')

    smoke = mapping(read_json(evidence / 'smoke.json'))

    if smoke.get('passed') is not True or any(
        smoke.get(field) != record[field]
        for field in (
            'source',
            'version',
            'digest',
            'runtimeDigest',
            'imageId',
            'archiveSha256',
        )
    ):
        raise ValueError('Missing or mismatched successful smoke evidence.')

    if (
        read_json(evidence / 'sbom.spdx.json') != info['sbom']
        or read_json(evidence / 'provenance.json') != info['provenance']
    ):
        raise ValueError('Retained attestations differ from the candidate.')

    decision = evaluate(
        read_json(evidence / 'vulnerabilities.json'),
        read_json(ROOT / 'security/container-vulnerability-exceptions.json'),
        expected=packages,
        production=packages,
        image_id=info['imageId'],
    )

    if (
        not decision['allowed']
        or mapping(read_json(evidence / 'gate.json')).get('allowed') is not True
    ):
        raise ValueError('Critical findings or invalid policy block publication.')

    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('mode', choices=['qualify', 'verify'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('evidence', type=Path)

    args = parser.parse_args()

    try:
        if args.mode == 'qualify':
            qualify(args.archive.resolve(), args.evidence.resolve())
        else:
            verify(args.archive.resolve(), args.evidence.resolve())

        return 0
    except Exception as error:
        args.evidence.mkdir(parents=True, exist_ok=True)
        write_json(
            args.evidence / 'failure.json', {'stage': args.mode, 'error': str(error)}
        )
        print(f'Release candidate blocked: {error}', file=sys.stderr)

        return 1


if __name__ == '__main__':
    sys.exit(main())
