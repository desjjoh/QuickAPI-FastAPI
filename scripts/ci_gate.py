"""Require explicit success from every mandatory Quality job."""

import json
import os
from pathlib import Path
from typing import Any

from scripts.security_policy import invalid_constant, mapping, unique_fields

REQUIRED_JOBS = (
    'dependency-security',
    'static-analysis',
    'test-layers',
    'mysql-tests',
    'combined-coverage',
    'production-container',
)


def evaluate(raw: str) -> dict[str, Any]:
    results = mapping(
        json.loads(
            raw, object_pairs_hook=unique_fields, parse_constant=invalid_constant
        )
    )

    if set(results) != set(REQUIRED_JOBS):
        raise ValueError('Missing or unexpected required job results.')

    outcomes = {name: mapping(results[name]).get('result') for name in REQUIRED_JOBS}

    return {
        'allowed': all(value == 'success' for value in outcomes.values()),
        'results': outcomes,
    }


def main() -> int:
    try:
        decision = evaluate(os.environ.get('NEEDS_JSON', ''))
    except (ValueError, TypeError) as error:
        decision = {'allowed': False, 'error': str(error)}

    output = Path('test-artifacts/ci-gate.json')

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(decision, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(decision, indent=2))

    return 0 if decision['allowed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
