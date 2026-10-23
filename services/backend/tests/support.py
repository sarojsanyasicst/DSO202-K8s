"""Safety helpers for tests that use the disposable dependencies.

Importable from test modules and conftest files (pytest `pythonpath` includes
this directory), so the guards themselves have unit tests.
"""

import os
from collections.abc import Mapping

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

POSTGRES_URL_VARIABLE = "CLOUDCART_TEST_POSTGRES_URL"
BROKER_URL_VARIABLE = "CLOUDCART_TEST_BROKER_URL"
TEST_ENVIRONMENT_VARIABLES = frozenset({POSTGRES_URL_VARIABLE, BROKER_URL_VARIABLE})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
# libpq reads these when the URL does not override them; either can route a
# connection to a different server than the URL's host.
LIBPQ_ROUTING_VARIABLES = ("PGHOSTADDR", "PGSERVICE")


def required_environment(variable: str) -> str:
    """Return a test-only setting, failing (never skipping) when it is missing."""
    value = os.environ.get(variable)
    if not value:
        pytest.fail(
            f"{variable} is not set. Start the disposable dependencies with `make test-deps-up` "
            "and run integration tests with `make test-integration`.",
            pytrace=False,
        )
    return value


def require_loopback(variable: str, host: str | None, query: Mapping[str, object]) -> None:
    """Refuse destructive test setup unless the URL can only reach a loopback host.

    Query parameters are refused outright: libpq accepts host, hostaddr, port and
    service there, each of which would route around the host check.
    """
    if host not in LOOPBACK_HOSTS:
        pytest.fail(
            f"{variable} must point at a loopback host ({', '.join(sorted(LOOPBACK_HOSTS))}); "
            f"refusing destructive test setup against {host!r}.",
            pytrace=False,
        )
    if query:
        pytest.fail(
            f"{variable} must not contain query parameters ({', '.join(sorted(query))}); "
            "they can redirect the connection away from the loopback host.",
            pytrace=False,
        )


def require_no_libpq_routing_overrides() -> None:
    """Refuse PostgreSQL setup while libpq environment variables could redirect the connection."""
    routing = [name for name in LIBPQ_ROUTING_VARIABLES if os.environ.get(name)]
    if routing:
        pytest.fail(
            f"Unset {', '.join(routing)} before running integration tests; "
            "libpq would use it to route away from the loopback host.",
            pytrace=False,
        )


def without_ambient_settings(environ: Mapping[str, str]) -> dict[str, str]:
    """Copy `environ` without CLOUDCART_* settings, keeping only the explicit test variables."""
    return {
        name: value
        for name, value in environ.items()
        if not name.startswith("CLOUDCART_") or name in TEST_ENVIRONMENT_VARIABLES
    }


def truncate_application_tables(connection: Connection) -> None:
    """Empty every public table except alembic_version and restart identity sequences."""
    tables = connection.execute(
        text(
            "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )
    ).scalars().all()
    if tables:
        connection.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
