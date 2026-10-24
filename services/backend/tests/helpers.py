"""API and SQL helpers shared by integration test modules (importable: pytest `pythonpath` includes this directory)."""

import time
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from cloudcart.db import Database

type OpenClient = Callable[..., TestClient]
LOCK_WAIT_TIMEOUT_SECONDS = 10


def run_sql(database: Database, statement: str, **parameters: object) -> list[Row]:
    """Run one statement in its own committed transaction; return its rows (empty when it returns none)."""
    with database.engine.begin() as connection:
        result = connection.execute(text(statement), parameters)
        return list(result.all()) if result.returns_rows else []


def backend_pid(session: Session) -> int:
    return session.execute(text("SELECT pg_backend_pid()")).scalar_one()


def wait_until_blocked(database: Database, pid: int, by: int) -> None:
    """Return once backend `pid` waits for a lock that backend `by` holds."""
    deadline = time.monotonic() + LOCK_WAIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        [(blocked,)] = run_sql(database, "SELECT :by = ANY(pg_blocking_pids(:pid))", by=by, pid=pid)
        if blocked:
            return
        time.sleep(0.02)
    pytest.fail(f"Backend {pid} never waited for backend {by}; the transactions did not overlap.")


@dataclass
class Browser:
    """A client plus the CSRF token returned when its session started."""

    client: TestClient
    csrf_token: str

    def send(
        self, method: str, url: str, body: object = None, csrf_token: str | None = None, **headers: str
    ) -> Response:
        if csrf_token is not None:
            headers["X-CSRF-Token"] = csrf_token
        return self.client.request(method, url, json=body, headers=headers)


def start_guest(client: TestClient) -> Browser:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    return Browser(client, response.json()["csrf_token"])
