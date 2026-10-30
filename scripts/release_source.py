"""Verify a main commit's latest push CI before building a release candidate."""

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts.security_policy import mapping, sequence

SHA = re.compile(r'[a-f0-9]{40}')
VERSION = re.compile(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?')


def api(path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        'https://api.github.com/' + path,
        headers={
            'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return mapping(json.load(response))


def validate_ci(
    run: dict[str, Any], jobs: list[Any], sha: str, repository: str
) -> None:
    if (
        run.get('head_sha') != sha
        or run.get('head_branch') != 'main'
        or run.get('event') != 'push'
        or run.get('status') != 'completed'
        or run.get('conclusion') != 'success'
        or run.get('name') != 'Quality'
        or mapping(run.get('head_repository')).get('full_name') != repository
    ):
        raise ValueError(
            'Latest exact-source main push CI must succeed in this repository.'
        )

    gates = [
        mapping(job) for job in jobs if mapping(job).get('name') == 'Deployment gate'
    ]

    if (
        len(gates) != 1
        or gates[0].get('conclusion') != 'success'
        or gates[0].get('status') != 'completed'
    ):
        raise ValueError(
            'The selected CI attempt must contain one successful Deployment gate.'
        )


def select_source() -> dict[str, Any]:
    sha, repository = os.environ.get('REQUESTED_SHA', ''), os.environ.get(
        'GITHUB_REPOSITORY', ''
    )

    if not SHA.fullmatch(sha) or not re.fullmatch(
        r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository
    ):
        raise ValueError('A full lowercase SHA and repository are required.')

    comparison = api(f'repos/{repository}/compare/{sha}...main')

    if (
        comparison.get('status') not in {'identical', 'ahead'}
        or mapping(comparison.get('merge_base_commit')).get('sha') != sha
    ):
        raise ValueError('Selected commit must belong to main.')

    query = urllib.parse.urlencode(
        {'head_sha': sha, 'event': 'push', 'branch': 'main', 'per_page': 100}
    )
    runs = sequence(
        api(f'repos/{repository}/actions/workflows/tests.yml/runs?{query}').get(
            'workflow_runs'
        )
    )

    if not runs:
        raise ValueError('No exact-source main push CI is available.')

    run = max((mapping(value) for value in runs), key=lambda value: int(value['id']))
    run_id, attempt = int(run['id']), int(run['run_attempt'])
    jobs: list[Any] = []
    page = 1

    while True:
        batch = sequence(
            api(
                f'repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}'
            ).get('jobs')
        )

        jobs.extend(batch)

        if len(batch) < 100:
            break

        page += 1

    validate_ci(run, jobs, sha, repository)

    registry = os.environ.get('REGISTRY', 'ghcr.io')
    image_repository = os.environ.get('IMAGE_REPOSITORY', repository).lower()

    if not re.fullmatch(r'[a-z0-9][a-z0-9.:-]*', registry) or not re.fullmatch(
        r'[a-z0-9]+(?:[._/-][a-z0-9]+)*', image_repository
    ):
        raise ValueError('Invalid release registry/repository.')

    return {
        'sha': sha,
        'repository': 'https://github.com/' + repository,
        'ciRunId': run_id,
        'ciAttempt': attempt,
        'image': registry + '/' + image_repository,
        'releaseRunId': os.environ.get('GITHUB_RUN_ID'),
        'releaseAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
    }


def release_version(root: Path) -> str:
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    example = [
        line.split('=', 1)[1]
        for line in (root / '.env.example').read_text(encoding='utf-8').splitlines()
        if line.startswith('APP_VERSION=')
    ]

    if not VERSION.fullmatch(version) or example != [version]:
        raise ValueError(
            'VERSION and .env.example APP_VERSION must agree on a release version.'
        )

    return version


def main() -> None:
    path = Path(os.environ['RELEASE_EVIDENCE'])

    path.mkdir(parents=True, exist_ok=True)

    try:
        source = select_source()
    except Exception as error:
        (path / 'failure.json').write_text(
            json.dumps({'stage': 'source', 'error': str(error)}) + '\n',
            encoding='utf-8',
        )

        raise

    (path / 'source.json').write_text(
        json.dumps(source, indent=2) + '\n', encoding='utf-8'
    )

    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
        output.write(f'sha={source["sha"]}\nimage={source["image"]}\n')


if __name__ == '__main__':
    main()
