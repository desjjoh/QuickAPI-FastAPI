"""Express-aligned dependency/image gates: python -m scripts.security_scan MODE."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.security_policy import (
    evaluate,
    mapping,
    read_json,
    requirements,
    sequence,
    text,
)

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r'sha256:[a-f0-9]{64}')


def run(arguments: list[str], output: Path) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, cwd=ROOT)

    with (output / 'commands.log').open('a', encoding='utf-8') as log:
        log.write(f'{arguments!r}\n{result.stderr}\n')

    if result.returncode != 0:
        raise RuntimeError(
            f'Security tool failed with exit {result.returncode}; see commands.log.'
        )

    return result.stdout


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)

    return digest.hexdigest()


def archive_identity(path: Path, image_id: str) -> None:
    with tarfile.open(path) as archive:
        manifest_member = archive.getmember('manifest.json')
        manifest_file = archive.extractfile(manifest_member)

        if manifest_file is None or manifest_member.size > 1024 * 1024:
            raise ValueError('Missing or oversized Docker archive manifest.')

        manifest = sequence(json.load(manifest_file))

        if len(manifest) != 1:
            raise ValueError('Expected one image in runtime archive.')

        config_member = archive.getmember(text(mapping(manifest[0]).get('Config')))
        config = archive.extractfile(config_member)

        if config is None or config_member.size > 16 * 1024 * 1024:
            raise ValueError('Missing or oversized image configuration.')

        if 'sha256:' + hashlib.sha256(config.read()).hexdigest() != image_id:
            raise ValueError(
                'Archive does not contain the qualified image configuration.'
            )


def scan(mode: str, image_id: str | None = None) -> bool:
    output = ROOT / 'test-artifacts' / 'security' / mode

    output.mkdir(parents=True, exist_ok=True)

    # A failed retry must never leave a previous successful decision/report behind.
    for name in (
        'result.json',
        'summary.md',
        'runtime.json',
        'full.json',
        'image.json',
        'identity.json',
    ):
        (output / name).unlink(missing_ok=True)

    try:
        production = requirements(ROOT / 'requirements.txt')
        development = requirements(ROOT / 'requirements-dev.txt')

        if production.keys() & development.keys():
            raise ValueError(
                'Runtime and development requirement declarations overlap.'
            )

        scanner = os.environ.get('TRIVY_SCANNER_IMAGE', 'aquasec/trivy:latest')

        run(['docker', 'pull', scanner], output)

        scanner_id = run(
            ['docker', 'image', 'inspect', '--format', '{{.Id}}', scanner], output
        ).strip()

        if not DIGEST.fullmatch(scanner_id):
            raise ValueError('Invalid scanner identity.')

        cache = ROOT / 'test-artifacts' / 'security' / 'trivy-cache'

        cache.mkdir(parents=True, exist_ok=True)

        base = [
            'docker',
            'run',
            '--rm',
            '--volume',
            f'{cache.resolve()}:/root/.cache/trivy',
        ]
        options = [
            '--scanners',
            'vuln',
            '--format',
            'json',
            '--list-all-pkgs',
            '--exit-code',
            '0',
            '--ignorefile',
            '/dev/null',
        ]
        decisions: list[dict[str, Any]] = []
        identity: dict[str, Any] = {
            'scannerReference': scanner,
            'scannerId': scanner_id,
        }

        write_json(output / 'identity.json', identity)

        with TemporaryDirectory(prefix='security-', dir=output) as temporary:
            temporary_path = Path(temporary)

            if mode == 'dependencies':
                policy = read_json(ROOT / 'security/dependency-audit-exceptions.json')

                for name, expected in (
                    ('runtime', production),
                    ('full', production | development),
                ):
                    source = temporary_path / name

                    source.mkdir()
                    (source / 'requirements.txt').write_text(
                        ''.join(
                            f'{package}=={version}\n'
                            for package, version in sorted(expected.items())
                        ),
                        encoding='utf-8',
                    )
                    report_text = run(
                        [
                            *base,
                            '--volume',
                            f'{source.resolve()}:/input:ro',
                            scanner_id,
                            'filesystem',
                            *options,
                            '/input',
                        ],
                        output,
                    )
                    report_path = output / f'{name}.json'

                    report_path.write_text(report_text, encoding='utf-8')
                    decisions.append(
                        evaluate(
                            read_json(report_path),
                            policy,
                            expected=expected,
                            production=production,
                        )
                    )

                identity['requirements'] = {
                    'runtime': production,
                    'development': development,
                }
            else:
                if image_id is None or not DIGEST.fullmatch(image_id):
                    raise ValueError(
                        'Image scan requires the immutable qualified image ID.'
                    )

                archive = temporary_path / 'runtime.tar'

                run(
                    ['docker', 'image', 'save', '--output', str(archive), image_id],
                    output,
                )
                archive_identity(archive, image_id)

                archive_hash = sha256(archive)

                identity.update(imageId=image_id, archiveSha256=archive_hash)
                write_json(output / 'identity.json', identity)
                report_text = run(
                    [
                        *base,
                        '--volume',
                        f'{temporary_path.resolve()}:/input:ro',
                        scanner_id,
                        'image',
                        *options,
                        '--input',
                        '/input/runtime.tar',
                    ],
                    output,
                )
                report_path = output / 'image.json'

                report_path.write_text(report_text, encoding='utf-8')

                if sha256(archive) != archive_hash:
                    raise ValueError('Runtime archive changed during scanning.')

                policy = read_json(
                    ROOT / 'security/container-vulnerability-exceptions.json'
                )

                decisions.append(
                    evaluate(
                        read_json(report_path),
                        policy,
                        expected=production,
                        production=production,
                        image_id=image_id,
                    )
                )
                identity.update(imageId=image_id, archiveSha256=archive_hash)

        identity['scannerVersion'] = run([*base, scanner_id, '--version'], output)

        write_json(output / 'identity.json', identity)

        allowed = all(decision['allowed'] for decision in decisions)
        findings = [
            finding for decision in decisions for finding in decision['findings']
        ]

        write_json(output / 'result.json', {'allowed': allowed, 'scans': decisions})

        summary = [
            f'# Security gate: {"PASS" if allowed else "BLOCKED"}',
            '',
            'Critical production/image findings block; development-only findings are nonblocking.',
            '',
        ]

        for finding in findings:
            line = (
                f'{finding["severity"]}: {finding["vulnerabilityId"]} '
                f'{finding["packageName"]}@{finding["installedVersion"]}; '
                f'development-only={finding["developmentOnly"]}; exception={finding["exception"]}'
            )

            summary.append(f'- {line}')

        for severity in ('CRITICAL', 'HIGH', 'MEDIUM'):
            count = sum(finding['severity'] == severity for finding in findings)

            if count:
                print(
                    f'::warning::{count} {severity} findings across scan reports; see retained evidence for scope and exceptions.'
                )

        (output / 'summary.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')

        return allowed
    except Exception as error:
        write_json(output / 'result.json', {'allowed': False, 'error': str(error)})
        (output / 'summary.md').write_text(
            '# Security gate: BLOCKED\n\nTool or evidence validation failed; see result.json and commands.log.\n',
            encoding='utf-8',
        )

        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('mode', choices=['dependencies', 'image'])
    parser.add_argument('--image')

    args = parser.parse_args()

    try:
        return 0 if scan(args.mode, args.image) else 1
    except Exception as error:
        print(f'Security gate failed: {error}', file=sys.stderr)

        return 1


if __name__ == '__main__':
    sys.exit(main())
