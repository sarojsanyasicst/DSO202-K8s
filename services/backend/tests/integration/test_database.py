"""Database foundation behaviour against the disposable PostgreSQL server."""

import time
from collections.abc import Iterator

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from cloudcart.config import Settings
from cloudcart.db import (
    KEEPALIVES_COUNT,
    KEEPALIVES_IDLE_SECONDS,
    KEEPALIVES_INTERVAL_SECONDS,
    TCP_USER_TIMEOUT_MS,
    Database,
)
from cloudcart.main import create_app
from support import truncate_application_tables

PROBE_TABLE = "session_scope_probe"


class ProbeFailure(Exception):
    pass


@pytest.fixture
def probe_table(database: Database) -> Iterator[str]:
    with database.engine.begin() as connection:
        connection.execute(text(f"CREATE TABLE {PROBE_TABLE} (label text PRIMARY KEY)"))
    yield PROBE_TABLE
    with database.engine.begin() as connection:
        connection.execute(text(f"DROP TABLE {PROBE_TABLE}"))


def committed_labels(database_url: str) -> list[str]:
    """Read through a new, independent connection so only committed rows are visible."""
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return list(connection.execute(text(f"SELECT label FROM {PROBE_TABLE} ORDER BY label")).scalars())
    finally:
        engine.dispose()


def test_migrations_bring_fresh_test_database_to_head(database: Database, alembic_config: Config) -> None:
    script_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())

    with database.session_scope() as session:
        database_name = session.execute(text("SELECT current_database()")).scalar_one()
        has_version_table = session.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar_one()
        applied_revisions = set(session.execute(text("SELECT version_num FROM alembic_version")).scalars())

    assert database_name.startswith("cloudcart_test_")
    assert has_version_table is True
    assert applied_revisions == script_heads


def test_session_scope_commits_on_success(database: Database, probe_table: str, test_database_url: str) -> None:
    with database.session_scope() as session:
        session.execute(text(f"INSERT INTO {probe_table} (label) VALUES ('committed')"))

    assert committed_labels(test_database_url) == ["committed"]


def test_session_scope_rolls_back_and_reraises_on_error(
    database: Database, probe_table: str, test_database_url: str
) -> None:
    with pytest.raises(ProbeFailure):
        with database.session_scope() as session:
            session.execute(text(f"INSERT INTO {probe_table} (label) VALUES ('discarded')"))
            session.flush()
            raise ProbeFailure

    assert committed_labels(test_database_url) == []


def test_database_sessions_use_bounded_timeouts(test_database_url: str) -> None:
    settings = Settings(
        database_url=SecretStr(test_database_url),
        db_connect_timeout_seconds=4,
        db_pool_timeout_seconds=3,
        db_statement_timeout_ms=200,
    )
    database = Database(settings)
    try:
        with database.session_scope() as session:
            assert session.execute(text("SHOW statement_timeout")).scalar_one() == "200ms"
            connection_parameters = session.connection().connection.dbapi_connection.info.get_parameters()
            assert connection_parameters["connect_timeout"] == "4"
            assert connection_parameters["keepalives"] == "1"
            assert connection_parameters["keepalives_idle"] == str(KEEPALIVES_IDLE_SECONDS)
            assert connection_parameters["keepalives_interval"] == str(KEEPALIVES_INTERVAL_SECONDS)
            assert connection_parameters["keepalives_count"] == str(KEEPALIVES_COUNT)
            assert connection_parameters["tcp_user_timeout"] == str(TCP_USER_TIMEOUT_MS)
        assert database.engine.pool.timeout() == 3

        with pytest.raises(OperationalError, match="statement timeout"):
            with database.session_scope() as session:
                session.execute(text("SELECT pg_sleep(2)"))
    finally:
        database.dispose()


def test_app_lifespan_closes_database_connections_on_shutdown(
    integration_settings: Settings, test_database_url: str
) -> None:
    app = create_app(integration_settings)

    with TestClient(app):
        with app.state.database.session_scope() as session:
            backend_pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert backend_is_connected(test_database_url, backend_pid)

    deadline = time.monotonic() + 5
    while backend_is_connected(test_database_url, backend_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not backend_is_connected(test_database_url, backend_pid)


def backend_is_connected(database_url: str, backend_pid: int) -> bool:
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid = :pid)"), {"pid": backend_pid}
            ).scalar_one()
    finally:
        engine.dispose()


def test_truncate_application_tables_empties_tables_and_keeps_alembic_version(database: Database) -> None:
    with database.engine.connect() as connection:
        transaction = connection.begin()  # rolled back, so the probe rows never persist
        try:
            connection.execute(
                text("CREATE TABLE truncate_probe (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, label text)")
            )
            connection.execute(text("INSERT INTO truncate_probe (label) VALUES ('first'), ('second')"))
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('probe_revision')"))
            versions_before = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())

            truncate_application_tables(connection)

            assert connection.execute(text("SELECT count(*) FROM truncate_probe")).scalar_one() == 0
            restarted_id = connection.execute(
                text("INSERT INTO truncate_probe (label) VALUES ('after') RETURNING id")
            ).scalar_one()
            assert restarted_id == 1
            assert set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars()) == versions_before
        finally:
            transaction.rollback()
