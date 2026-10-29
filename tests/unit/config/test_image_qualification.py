import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import test_image

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('failure', ['database_start', 'http_checks', 'artifact_write'])
def test_image_failure_always_removes_disposable_project(
    failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if (failure == 'database_start' and 'up' in arguments) or (
            failure == 'http_checks' and test_image.HTTP_CHECKS in arguments
        ):
            raise subprocess.CalledProcessError(
                1, arguments, output='Test failure', stderr='Test diagnostic'
            )
        result = 'Application exited cleanly'
        if 'inspect' in arguments:
            result = '0'
        if 'ps' in arguments:
            result = 'test-container-id'
        return subprocess.CompletedProcess(arguments, 0, stdout=result, stderr='')

    monkeypatch.setattr(test_image, 'ROOT', tmp_path)
    monkeypatch.setattr(test_image.subprocess, 'run', run)
    if failure == 'artifact_write':

        def denied(*_: Any, **__: Any) -> None:
            raise PermissionError('Injected artifact failure')

        monkeypatch.setattr(Path, 'write_text', denied)
    with pytest.raises((subprocess.CalledProcessError, PermissionError)):
        test_image.qualify('quickapi-fastapi:test')
    assert calls[-1][-3:] == ['down', '--volumes', '--remove-orphans']
    assert 'quickapi-fastapi-smoke' in calls[-1]
    assert all('quickapi-fastapi-dev' not in command for command in calls)
