"""Shared pytest fixtures for CloudCart backend tests.

Integration fixtures use the disposable dependencies from tests/compose.yaml
(`make test-deps-up`). `make test-integration` exports the TEST-ONLY settings
CLOUDCART_TEST_POSTGRES_URL and CLOUDCART_TEST_BROKER_URL. Fixtures refuse to
run destructive setup unless those URLs can only reach a loopback host, and
fail with instructions instead of skipping when a dependency is missing.

Isolation: each pytest session creates one fresh PostgreSQL database, migrates
it with `alembic upgrade head` through the real Alembic configuration, and
drops it at the end. integration/conftest.py empties every application table
after each integration test and hides ambient CLOUDCART_* settings. Tests may
open several independent connections, and subprocesses can reach the same
database through `test_database_url`.
"""

import os
import secrets
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from cloudcart.config import Settings
from cloudcart.db import Database
from support import (
    BROKER_URL_VARIABLE,
    POSTGRES_URL_VARIABLE,
    require_loopback,
    require_no_libpq_routing_overrides,
    required_environment,
    without_ambient_settings,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
DEPENDENCY_TIMEOUT_SECONDS = 3
MIGRATION_TIMEOUT_SECONDS = 120
AMQP_DEFAULT_PORT = 5672


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(scope="session")
def postgres_server_url() -> URL:
    """Maintenance-database URL of the disposable PostgreSQL server."""
    url = make_url(required_environment(POSTGRES_URL_VARIABLE))
    require_loopback(POSTGRES_URL_VARIABLE, url.host, url.query)
    require_no_libpq_routing_overrides()
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
        env={**without_ambient_settings(os.environ), "CLOUDCART_DATABASE_URL": database_url},
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
    """Database bound to the session's test database."""
    database = Database(integration_settings)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture(scope="session")
def test_broker_url() -> str:
    """AMQP URL of the disposable RabbitMQ, shared by tests and worker subprocesses."""
    url = required_environment(BROKER_URL_VARIABLE)
    parts = urlsplit(url)
    require_loopback(BROKER_URL_VARIABLE, parts.hostname, parse_qs(parts.query))
    unavailable = None
    try:
        socket.create_connection(
            (parts.hostname, parts.port or AMQP_DEFAULT_PORT), timeout=DEPENDENCY_TIMEOUT_SECONDS
        ).close()
    except OSError as error:
        unavailable = str(error)
    if unavailable is not None:
        pytest.fail(
            f"Disposable RabbitMQ at {parts.hostname}:{parts.port or AMQP_DEFAULT_PORT} is unavailable "
            f"({unavailable}). Start it with `make test-deps-up`.",
            pytrace=False,
        )
    return url
