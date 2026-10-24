"""Database engine and session lifecycle for the API, worker, and migrations."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from cloudcart.config import Settings

# TCP keepalive and user-timeout bounds for established connections. statement_timeout
# is enforced by the server, so these detect a dead or paused peer from the client side
# (about 30 s instead of the operating-system defaults of minutes to hours). libpq
# ignores tcp_user_timeout where the OS lacks it (e.g. macOS); the Linux images use it.
KEEPALIVES_IDLE_SECONDS = 15
KEEPALIVES_INTERVAL_SECONDS = 5
KEEPALIVES_COUNT = 3
TCP_USER_TIMEOUT_MS = 30_000

# Deterministic constraint names keep Alembic revisions reviewable and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every CloudCart table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Database:
    """One engine and session factory per process (API app, worker, or migration run).

    `session_factory` is a `Callable[[], Session]` for code that manages its own
    transactions; most callers use `session_scope()`.
    """

    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            pool_timeout=settings.db_pool_timeout_seconds,
            connect_args={
                "connect_timeout": settings.db_connect_timeout_seconds,
                "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
                "keepalives": 1,
                "keepalives_idle": KEEPALIVES_IDLE_SECONDS,
                "keepalives_interval": KEEPALIVES_INTERVAL_SECONDS,
                "keepalives_count": KEEPALIVES_COUNT,
                "tcp_user_timeout": TCP_USER_TIMEOUT_MS,
            },
        )
        # Objects stay readable after commit, e.g. to build an HTTP response.
        self.session_factory: sessionmaker[Session] = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Yield a session that commits when the block succeeds and rolls back, then re-raises, when it fails."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Close pooled connections, e.g. on application shutdown."""
        self.engine.dispose()


def request_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one transaction per request, using the application's Database."""
    database: Database = request.app.state.database
    with database.session_scope() as session:
        yield session


# "function" scope commits (or rolls back) when the route returns or raises, before the
# response is sent, so a client never sees success for a change that failed to commit.
DbSession = Annotated[Session, Depends(request_session, scope="function")]
