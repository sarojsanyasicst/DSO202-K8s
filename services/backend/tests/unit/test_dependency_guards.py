"""Regression tests for the safety guards in tests/support.py (no Docker needed)."""

import pytest
from sqlalchemy.engine import make_url

from support import (
    POSTGRES_URL_VARIABLE,
    require_loopback,
    require_no_libpq_routing_overrides,
    required_environment,
    without_ambient_settings,
)

LOOPBACK_URL = "postgresql+psycopg://cloudcart_test:pw@127.0.0.1:15432/postgres"


def check_postgres_url(raw_url: str) -> None:
    """Apply the guard exactly as the postgres_server_url fixture does."""
    url = make_url(raw_url)
    require_loopback(POSTGRES_URL_VARIABLE, url.host, url.query)


@pytest.mark.parametrize(
    "raw_url",
    [
        LOOPBACK_URL,
        "postgresql+psycopg://cloudcart_test:pw@localhost:15432/postgres",
        "postgresql+psycopg://cloudcart_test:pw@[::1]:15432/postgres",
    ],
)
def test_loopback_guard_accepts_loopback_hosts(raw_url: str) -> None:
    check_postgres_url(raw_url)


def test_loopback_guard_rejects_a_remote_host() -> None:
    with pytest.raises(pytest.fail.Exception, match="refusing destructive test setup against 'db.example.com'"):
        check_postgres_url("postgresql+psycopg://cloudcart_test:pw@db.example.com:5432/postgres")


@pytest.mark.parametrize(
    "query",
    ["host=db.example.com", "hostaddr=192.0.2.10", "service=production", "port=5432", "sslmode=disable"],
)
def test_loopback_guard_rejects_query_parameters_that_could_reroute(query: str) -> None:
    with pytest.raises(pytest.fail.Exception, match="must not contain query parameters"):
        check_postgres_url(f"{LOOPBACK_URL}?{query}")


@pytest.mark.parametrize("variable", ["PGHOSTADDR", "PGSERVICE"])
def test_libpq_routing_variables_are_refused(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    monkeypatch.setenv(variable, "192.0.2.10")

    with pytest.raises(pytest.fail.Exception, match=f"Unset {variable}"):
        require_no_libpq_routing_overrides()


def test_libpq_routing_check_passes_without_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PGHOSTADDR", raising=False)
    monkeypatch.delenv("PGSERVICE", raising=False)

    require_no_libpq_routing_overrides()


def test_missing_test_setting_fails_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(POSTGRES_URL_VARIABLE, raising=False)

    with pytest.raises(BaseException) as raised:
        required_environment(POSTGRES_URL_VARIABLE)

    assert isinstance(raised.value, pytest.fail.Exception)
    assert not isinstance(raised.value, pytest.skip.Exception)
    assert "make test-deps-up" in str(raised.value)


def test_present_test_setting_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(POSTGRES_URL_VARIABLE, LOOPBACK_URL)

    assert required_environment(POSTGRES_URL_VARIABLE) == LOOPBACK_URL


def test_ambient_settings_are_removed_but_test_settings_kept() -> None:
    environ = {
        "CLOUDCART_DB_STATEMENT_TIMEOUT_MS": "1",
        "CLOUDCART_LAB_ENABLED": "true",
        "CLOUDCART_TEST_POSTGRES_URL": LOOPBACK_URL,
        "CLOUDCART_TEST_BROKER_URL": "amqp://u:p@127.0.0.1:15672//",
        "PATH": "/usr/bin",
    }

    assert without_ambient_settings(environ) == {
        "CLOUDCART_TEST_POSTGRES_URL": LOOPBACK_URL,
        "CLOUDCART_TEST_BROKER_URL": "amqp://u:p@127.0.0.1:15672//",
        "PATH": "/usr/bin",
    }
