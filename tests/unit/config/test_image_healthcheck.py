import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    'compose_file',
    ['docker-compose.yaml', 'docker-compose.smoke.yml', 'docker-compose.rollback.yml'],
)
@pytest.mark.parametrize('status', [200, 503])
def test_python_probe_requires_readiness_and_bypasses_proxies(
    compose_file: str, status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration: dict[str, Any] = yaml.safe_load((ROOT / compose_file).read_text())
    probe: list[str] = configuration['services']['api']['healthcheck']['test']
    response = Mock()
    opener = Mock()
    opener.open.return_value = response

    if status == 503:
        opener.open.side_effect = urllib.error.HTTPError(
            'http://127.0.0.1:8000/ready', 503, 'Not ready', Message(), None
        )

    factory = Mock(return_value=opener)

    monkeypatch.setattr(urllib.request, 'build_opener', factory)

    assert probe[:3] == ['CMD', 'python', '-c']

    if status == 503:
        with pytest.raises(urllib.error.HTTPError):
            exec(compile(probe[3], compose_file, 'exec'))
    else:
        exec(compile(probe[3], compose_file, 'exec'))

        response.close.assert_called_once()

    opener.open.assert_called_once_with('http://127.0.0.1:8000/ready', timeout=2)
    assert factory.call_args.args[0].proxies == {}
