import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from scripts import ci_gate

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]


def successful_jobs() -> dict[str, dict[str, str]]:
    return {name: {'result': 'success'} for name in ci_gate.REQUIRED_JOBS}


def test_gate_accepts_all_success() -> None:
    assert ci_gate.evaluate(json.dumps(successful_jobs()))['allowed']


@pytest.mark.parametrize('job', ci_gate.REQUIRED_JOBS)
@pytest.mark.parametrize('result', ['failure', 'cancelled', 'skipped', '', 'unknown'])
def test_gate_blocks_each_non_success(job: str, result: str) -> None:
    results = successful_jobs()

    results[job]['result'] = result

    assert not ci_gate.evaluate(json.dumps(results))['allowed']


@pytest.mark.parametrize('job', ci_gate.REQUIRED_JOBS)
def test_gate_blocks_missing_job(job: str) -> None:
    results = successful_jobs()

    results.pop(job)

    with pytest.raises(ValueError, match='Missing'):
        ci_gate.evaluate(json.dumps(results))


@pytest.mark.parametrize('raw', ['', 'null', '[]', '{}', '{"x":NaN}', '{"x":1,"x":2}'])
def test_malformed_context_blocks(
    raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NEEDS_JSON', raw)

    assert ci_gate.main() == 1
    assert (
        json.loads((tmp_path / 'test-artifacts/ci-gate.json').read_text())['allowed']
        is False
    )


def test_gate_writes_decision_and_returns_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NEEDS_JSON', json.dumps(successful_jobs()))

    assert ci_gate.main() == 0
    assert (
        json.loads((tmp_path / 'test-artifacts/ci-gate.json').read_text())['allowed']
        is True
    )


@pytest.mark.parametrize('value', [None, [], {}, {'result': None}])
def test_gate_rejects_malformed_job_result(value: Any) -> None:
    results: dict[str, Any] = successful_jobs()

    results['static-analysis'] = value

    try:
        decision = ci_gate.evaluate(json.dumps(results))
    except ValueError:
        return

    assert not decision['allowed']


def test_gate_rejects_unexpected_jobs() -> None:
    results = successful_jobs()

    results['untracked'] = {'result': 'success'}

    with pytest.raises(ValueError, match='unexpected'):
        ci_gate.evaluate(json.dumps(results))


def workflow() -> dict[str, Any]:
    # BaseLoader preserves GitHub's `on` key rather than interpreting YAML 1.1 booleans.
    return cast(
        dict[str, Any],
        yaml.load(
            (ROOT / '.github/workflows/tests.yml').read_text(encoding='utf-8'),
            Loader=yaml.BaseLoader,
        ),
    )


def test_workflow_covers_every_job_and_keeps_failure_enforcement() -> None:
    document = workflow()
    jobs = document['jobs']
    gate = jobs['deployment-gate']

    assert gate['name'] == 'Deployment gate'
    assert gate['if'] == 'always()'
    assert set(gate['needs']) == set(ci_gate.REQUIRED_JOBS)
    assert set(jobs) == {*ci_gate.REQUIRED_JOBS, 'deployment-gate'}
    assert any(
        step.get('run') == 'python -m scripts.ci_gate'
        and step['env']['NEEDS_JSON'] == '${{ toJSON(needs) }}'
        for step in gate['steps']
    )

    for job in jobs.values():
        assert job.get('continue-on-error', 'false') == 'false'
        assert all(
            step.get('continue-on-error', 'false') == 'false' for step in job['steps']
        )

    assert jobs['mysql-tests']['strategy']['matrix']['layer'] == ['integration', 'e2e']
    assert jobs['test-layers']['strategy']['matrix']['layer'] == ['unit']


def test_workflow_retains_required_triggers_and_bounded_evidence() -> None:
    document = workflow()
    events = document['on']

    assert set(events) == {
        'pull_request',
        'push',
        'merge_group',
        'workflow_dispatch',
        'workflow_call',
    }
    assert events['push']['branches'] == ['main', 'staging', 'dev']

    for job in document['jobs'].values():
        for step in job['steps']:
            if step.get('uses', '').startswith('actions/upload-artifact@'):
                assert step['if'] == 'always()'
                assert step['with']['retention-days'] == '14'
                assert 'test-artifacts/' not in step['with']['path'].splitlines()
                assert 'trivy' not in step['with']['path']
