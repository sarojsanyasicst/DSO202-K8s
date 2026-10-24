"""API and SQL helpers shared by integration test modules (importable: pytest `pythonpath` includes this directory)."""

from collections.abc import Callable
from dataclasses import dataclass

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Row, text

from cloudcart.db import Database

type OpenClient = Callable[..., TestClient]


def run_sql(database: Database, statement: str, **parameters: object) -> list[Row]:
    """Run one statement in its own committed transaction; return its rows (empty when it returns none)."""
    with database.engine.begin() as connection:
        result = connection.execute(text(statement), parameters)
        return list(result.all()) if result.returns_rows else []


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
