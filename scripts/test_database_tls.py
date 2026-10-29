"""Ephemeral CA/server certificates and a dedicated disposable TLS MySQL server."""

import ipaddress
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from scripts.test_database_support import ROOT, TestDatabaseConfig, load_test_config


def certificates(path: Path) -> None:
    now = datetime.now(UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Disposable MySQL Test CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("mysql-tls-test"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    (path / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (path / "server-cert.pem").write_bytes(
        server.public_bytes(serialization.Encoding.PEM)
    )
    (path / "server-key.pem").write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    untrusted = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(other.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(other, hashes.SHA256())
    )
    (path / "untrusted-ca.pem").write_bytes(
        untrusted.public_bytes(serialization.Encoding.PEM)
    )
    # This directory is bind-mounted into MySQL, which drops root privileges.
    # Linux TemporaryDirectory defaults to 0700; Docker Desktop masks that issue.
    # These disposable test credentials must be readable across host/container UIDs.
    for name in ("ca.pem", "server-cert.pem", "server-key.pem", "untrusted-ca.pem"):
        (path / name).chmod(0o644)
    path.chmod(0o755)


def run_tls(config: TestDatabaseConfig) -> int:
    raw = config.values.get("TEST_TLS_PORT", "3312")
    if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= 65535:
        raise ValueError(
            "TEST_TLS_PORT must be a whole port number from 1 through 65535."
        )
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mysql-tls-', dir=cache) as temporary:
        path = Path(temporary)
        certificates(path)
        env = {
            **os.environ,
            **config.values,
            "TEST_TLS_PORT": raw,
            "TEST_TLS_DIR": str(path.resolve()),
        }
        command = [
            'docker',
            'compose',
            '--env-file',
            str(ROOT / '.env.test'),
            '-p',
            'quickapi-fastapi-tls-test',
            '-f',
            str(ROOT / 'docker-compose.test.tls.yml'),
        ]
        result = 1
        try:
            result = subprocess.call(
                [*command, 'up', '-d', '--wait'], env=env, cwd=ROOT
            )
            if result:
                return result
            result = 1
            url = config.url.set(host='127.0.0.1', port=int(raw))
            load_test_config(
                {
                    **config.values,
                    'TEST_DATABASE_URL': url.render_as_string(hide_password=False),
                    'TEST_MYSQL_PORT': raw,
                }
            )
            child = {
                **env,
                'QUICKAPI_TEST_DATABASE': 'sqlite',
                'QUICKAPI_TEST_TLS': 'true',
                'TEST_MYSQL_PORT': raw,
                'TEST_DATABASE_URL': url.render_as_string(hide_password=False),
                'TEST_TLS_CA_FILE': str(path / 'ca.pem'),
                'TEST_TLS_UNTRUSTED_CA_FILE': str(path / 'untrusted-ca.pem'),
            }
            result = subprocess.call(
                [
                    sys.executable,
                    '-m',
                    'pytest',
                    '-q',
                    '--no-cov',
                    'tests/integration/database/test_database_tls.py',
                ],
                env=child,
                cwd=ROOT,
            )
            return result
        finally:
            logs = subprocess.run(
                [*command, 'logs', '--no-color', '--tail', '100'],
                env=env,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            artifacts = ROOT / 'test-artifacts'
            artifacts.mkdir(exist_ok=True)
            (artifacts / 'mysql-tls.log').write_text(
                logs.stdout + logs.stderr, encoding='utf-8'
            )
            if result:
                print(logs.stdout + logs.stderr)
            cleanup = subprocess.call(
                [*command, 'down', '--volumes'], env=env, cwd=ROOT
            )
            if cleanup and result == 0:
                raise RuntimeError('TLS test cleanup failed.')
