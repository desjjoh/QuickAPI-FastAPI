import os
import stat
from pathlib import Path

import pytest

from scripts.test_database_tls import certificates

pytestmark = pytest.mark.unit


def test_generated_tls_files_are_readable_by_container_user(tmp_path: Path) -> None:
    directory = tmp_path / 'certificates'

    directory.mkdir(mode=0o700)
    certificates(directory)
    assert {p.name for p in directory.iterdir()} == {
        'ca.pem',
        'server-cert.pem',
        'server-key.pem',
        'untrusted-ca.pem',
    }
    if os.name != 'nt':
        assert stat.S_IMODE(directory.stat().st_mode) == 0o755
        for path in directory.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o644
