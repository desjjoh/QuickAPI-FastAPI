"""Fail-closed Trivy evidence validation and Express-aligned critical-only policy."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

SCOPE = (
    'vulnerabilityId',
    'packageName',
    'installedVersion',
    'packagePath',
    'target',
    'type',
)
SEVERITIES = {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}


def text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError('Expected bounded nonempty text.')

    return value


def mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError('Expected an object.')

    return cast(dict[str, Any], value)


def sequence(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError('Expected a list.')

    return cast(list[Any], value)


def normalize(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}

    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()

        if not line or line.startswith('#') or line == '-r requirements.txt':
            continue

        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9.+!-]+)', line)

        if not match:
            raise ValueError(f'Unsupported unpinned requirement in {path.name}.')

        name, version = normalize(match[1]), match[2]

        if name in result:
            raise ValueError('Duplicate requirement.')

        result[name] = version

    if not result:
        raise ValueError('Empty requirements inventory.')

    return result


def exceptions(policy: Any, now: datetime) -> set[tuple[Any, ...]]:
    policy = mapping(policy)

    if policy.get('version') != 1:
        raise ValueError('Unsupported exception policy.')

    rules: set[tuple[Any, ...]] = set()

    for raw in sequence(policy.get('exceptions')):
        entry = mapping(raw)

        if set(entry) != {*SCOPE, 'owner', 'reason', 'review', 'expiresOn'}:
            raise ValueError('Invalid exception fields.')

        for field in (*SCOPE, 'owner', 'reason', 'review'):
            if field == 'packagePath' and entry[field] is None:
                continue

            value = text(entry[field])

            if field in SCOPE and any(char in value for char in '*?'):
                raise ValueError('Wildcard exceptions are forbidden.')

        expiry = text(entry['expiresOn'])

        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', expiry):
            raise ValueError('Invalid exception expiry.')

        deadline = datetime.strptime(expiry, '%Y-%m-%d').replace(tzinfo=UTC)

        if not now < deadline <= now + timedelta(days=30):
            raise ValueError('Exception expired or exceeds 30 days.')

        key = tuple(entry[field] for field in SCOPE)

        if key in rules:
            raise ValueError('Duplicate exception scope.')

        rules.add(key)

    return rules


def evaluate(
    report: Any,
    policy: Any,
    *,
    expected: dict[str, str],
    production: dict[str, str],
    image_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    rules = exceptions(policy, now)
    report = mapping(report)

    if report.get('SchemaVersion') != 2 or report.get('ArtifactType') != (
        'container_image' if image_id else 'filesystem'
    ):
        raise ValueError('Unsupported or incomplete scan report.')

    if image_id:
        metadata = mapping(report.get('Metadata'))
        os_info = mapping(metadata.get('OS'))

        if metadata.get('ImageID') != image_id:
            raise ValueError('Scan does not identify the qualified image.')

        if text(os_info.get('Family')) == 'unknown' or os_info.get('EOSL') is True:
            raise ValueError('Unsupported or end-of-life image OS.')

        text(os_info.get('Name'))

    inventory: set[tuple[str, str]] = set()
    os_packages = False
    findings: list[dict[str, Any]] = []

    for raw in sequence(report.get('Results')):
        result = mapping(raw)
        target, kind = text(result.get('Target')), text(result.get('Type'))
        packages = sequence(result.get('Packages'))
        entries: set[tuple[str, str]] = set()

        for raw_package in packages:
            package = mapping(raw_package)

            entries.add((text(package.get('Name')), text(package.get('Version'))))

        if result.get('Class') == 'lang-pkgs' and kind == (
            'python-pkg' if image_id else 'pip'
        ):
            inventory.update((normalize(name), version) for name, version in entries)

        if result.get('Class') == 'os-pkgs' and entries:
            os_packages = True

        for raw_finding in sequence(result.get('Vulnerabilities', [])):
            vulnerability = mapping(raw_finding)
            name = text(vulnerability.get('PkgName'))
            version = text(vulnerability.get('InstalledVersion'))
            severity = text(vulnerability.get('Severity'))

            if severity not in SEVERITIES or (name, version) not in entries:
                raise ValueError('Invalid severity or vulnerability outside inventory.')

            package_path = vulnerability.get('PkgPath')

            if package_path is not None:
                text(package_path)

            finding: dict[str, Any] = dict(
                zip(
                    SCOPE,
                    (
                        text(vulnerability.get('VulnerabilityID')),
                        name,
                        version,
                        package_path,
                        target,
                        kind,
                    ),
                    strict=True,
                )
            )
            development = (
                not image_id and (normalize(name), version) not in production.items()
            )

            if not image_id and expected.get(normalize(name)) != version:
                raise ValueError('Finding outside declared requirements.')

            finding.update(
                severity=severity,
                developmentOnly=development,
                exception=tuple(finding[field] for field in SCOPE) in rules,
                fixedVersion=vulnerability.get('FixedVersion'),
            )
            findings.append(finding)

    if not set(expected.items()) <= inventory or (image_id and not os_packages):
        raise ValueError('Missing Python requirements or OS inventory coverage.')

    blocked = [
        entry
        for entry in findings
        if entry['severity'] == 'CRITICAL'
        and not entry['developmentOnly']
        and not entry['exception']
    ]

    return {
        'allowed': not blocked,
        'blocked': blocked,
        'findings': findings,
        'evaluatedAt': now.isoformat(),
    }


def unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}

    for name, field in pairs:
        if name in value:
            raise ValueError('Duplicate JSON field.')

        value[name] = field

    return value


def invalid_constant(value: str) -> Any:
    raise ValueError(f'Invalid JSON constant: {value}')


def read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding='utf-8'),
        object_pairs_hook=unique_fields,
        parse_constant=invalid_constant,
    )
