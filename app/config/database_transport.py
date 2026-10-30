"""One engine/transport policy for application, migration, and verification callers."""

import asyncio
import importlib
import ssl
from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.common.handlers.database_pool import BoundedAsyncPool, DatabaseUnavailableError


@dataclass(frozen=True)
class DatabasePolicy:
    connection_limit: int = 10
    queue_limit: int = 50
    acquire_timeout_ms: int = 1000
    connect_timeout_ms: int = 10000
    ssl_enabled: bool = False
    ca_file: str | None = None

    def __post_init__(self) -> None:
        for value, lower, upper in (
            (self.connection_limit, 1, 1000),
            (self.queue_limit, 0, 10000),
            (self.acquire_timeout_ms, 1, 2147483647),
            (self.connect_timeout_ms, 1, 2147483647),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError("Invalid database capacity or deadline policy.")


def configured_policy() -> DatabasePolicy:
    from app.config.environment import settings

    return DatabasePolicy(
        settings.DB_POOL_CONNECTION_LIMIT,
        settings.DB_POOL_QUEUE_LIMIT,
        settings.DB_POOL_ACQUIRE_TIMEOUT_MS,
        settings.DB_CONNECT_TIMEOUT_MS,
        settings.DB_SSL,
        settings.DB_SSL_CA_FILE,
    )


def tls_context(policy: DatabasePolicy) -> ssl.SSLContext | None:
    if not policy.ssl_enabled:
        if policy.ca_file is not None:
            raise ValueError("DB_SSL_CA_FILE requires DB_SSL=true.")

        return None

    try:
        context = ssl.create_default_context(cafile=policy.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        return context
    except (OSError, ssl.SSLError):
        raise ValueError("Unable to load valid database CA certificates.") from None


def build_database_engine(
    database_url: str | URL, *, policy: DatabasePolicy | None = None
) -> AsyncEngine:
    policy = configured_policy() if policy is None else policy
    url = make_url(database_url)
    context = tls_context(policy)

    if url.drivername != "mysql+asyncmy" or set(url.query) - {"charset"}:
        raise ValueError(
            "MySQL requires asyncmy; only the charset URL option is supported."
        )

    async def creator() -> Any:
        driver = importlib.import_module("asyncmy")
        _, arguments = engine.dialect.create_connect_args(url)
        connection: Any = driver.Connection(
            **arguments, connect_timeout=policy.connect_timeout_ms / 1000, ssl=context
        )

        try:
            async with asyncio.timeout(policy.connect_timeout_ms / 1000):
                await connection.connect()
                if context is not None:
                    async with connection.cursor() as cursor:
                        await cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
                        cipher = await cursor.fetchone()

                        if cipher is None or not cipher[1]:
                            raise DatabaseUnavailableError("DB_TLS_REQUIRED")

            return connection
        except TimeoutError:
            connection.close()

            raise DatabaseUnavailableError("DB_CONNECT_TIMEOUT") from None
        except asyncio.CancelledError:
            connection.close()

            raise
        except DatabaseUnavailableError:
            connection.close()

            raise
        except Exception:
            connection.close()

            raise DatabaseUnavailableError("DB_CONNECTION_FAILED") from None

    queue_limit = policy.queue_limit
    acquire_seconds = policy.acquire_timeout_ms / 1000

    class ConfiguredPool(BoundedAsyncPool):
        policy_queue_limit = queue_limit
        policy_acquire_timeout = acquire_seconds

    engine = create_async_engine(
        url,
        echo=False,
        hide_parameters=True,
        async_creator=creator,
        poolclass=ConfiguredPool,
        pool_size=policy.connection_limit,
        max_overflow=0,
        pool_timeout=policy.acquire_timeout_ms / 1000,
    )

    return engine
