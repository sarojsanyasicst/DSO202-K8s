"""Shared pytest fixtures for CloudCart backend tests.

Integration fixtures use the disposable dependencies from tests/compose.yaml
(`make test-deps-up`). `make test-integration` exports the TEST-ONLY settings
CLOUDCART_TEST_POSTGRES_URL and CLOUDCART_TEST_BROKER_URL. Fixtures refuse to
run destructive setup unless those URLs point at a loopback host, and fail
with instructions instead of skipping when a dependency is missing.

Isolation: each pytest session creates one fresh PostgreSQL database, migrates
it with `alembic upgrade head` through the real Alembic configuration, and
drops it at the end. The `database` fixture empties every application table
after each test. Tests may open several independent connections, and
subprocesses can reach the same database through `test_database_url`.
"""

import os
import secrets
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from cloudcart.config import Settings
from cloudcart.db import Database

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
POSTGRES_URL_VARIABLE = "CLOUDCART_TEST_POSTGRES_URL"
BROKER_URL_VARIABLE = "CLOUDCART_TEST_BROKER_URL"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
DEPENDENCY_TIMEOUT_SECONDS = 3
MIGRATION_TIMEOUT_SECONDS = 120


def _required_environment(variable: str) -> str:
    value = os.environ.get(variable)
    if not value:
        pytest.fail(
            f"{variable} is not set. Start the disposable dependencies with `make test-deps-up` "
            "and run integration tests with `make test-integration`.",
            pytrace=False,
        )
    return value


def _require_loopback(variable: str, host: str | None) -> None:
    if host not in LOOPBACK_HOSTS:
        pytest.fail(
            f"{variable} must point at a loopback host ({', '.join(sorted(LOOPBACK_HOSTS))}); "
            f"refusing destructive test setup against {host!r}.",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(scope="session")
def postgres_server_url() -> URL:
    """Maintenance-database URL of the disposable PostgreSQL server."""
    url = make_url(_required_environment(POSTGRES_URL_VARIABLE))
    _require_loopback(POSTGRES_URL_VARIABLE, url.host)
    return url


@pytest.fixture(scope="session")
def test_database_url(postgres_server_url: URL) -> Iterator[str]:
    """URL of a fresh, fully migrated database that exists for this pytest session only."""
    database_name = f"cloudcart_test_{secrets.token_hex(6)}"
    server = create_engine(
        postgres_server_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": DEPENDENCY_TIMEOUT_SECONDS},
    )
    unavailable = None
    try:
        with server.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except OperationalError as error:
        unavailable = str(error.orig)
    if unavailable is not None:
        server.dispose()
        pytest.fail(
            f"Disposable PostgreSQL at {postgres_server_url.host}:{postgres_server_url.port} is unavailable "
            f"({unavailable}). Start it with `make test-deps-up`.",
            pytrace=False,
        )

    database_url = postgres_server_url.set(database=database_name).render_as_string(hide_password=False)
    try:
        _upgrade_to_head(database_url)
        yield database_url
    finally:
        with server.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        server.dispose()


def _upgrade_to_head(database_url: str) -> None:
    """Run the same `alembic upgrade head` command a migration Job runs."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        env={**os.environ, "CLOUDCART_DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        timeout=MIGRATION_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"`alembic upgrade head` failed on the test database:\n{result.stderr}", pytrace=False)


@pytest.fixture
def integration_settings(test_database_url: str) -> Settings:
    return Settings(database_url=SecretStr(test_database_url))


@pytest.fixture
def database(integration_settings: Settings) -> Iterator[Database]:
    """Database bound to the session's test database; application tables are emptied afterwards."""
    database = Database(integration_settings)
    try:
        yield database
    finally:
        try:
            with database.engine.begin() as connection:
                _truncate_application_tables(connection)
        finally:
            database.dispose()


def _truncate_application_tables(connection: Connection) -> None:
    tables = connection.execute(
        text(
            "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )
    ).scalars().all()
    if tables:
        connection.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def test_broker_url() -> str:
    """AMQP URL of the disposable RabbitMQ, shared by tests and worker subprocesses."""
    url = _required_environment(BROKER_URL_VARIABLE)
    parts = urlsplit(url)
    _require_loopback(BROKER_URL_VARIABLE, parts.hostname)
    unavailable = None
    try:
        socket.create_connection((parts.hostname, parts.port or 5672), timeout=DEPENDENCY_TIMEOUT_SECONDS).close()
    except OSError as error:
        unavailable = str(error)
    if unavailable is not None:
        pytest.fail(
            f"Disposable RabbitMQ at {parts.hostname}:{parts.port} is unavailable ({unavailable}). "
            "Start it with `make test-deps-up`.",
            pytrace=False,
        )
    return url
