"""Isolation applied to every integration test, whichever fixtures it requests, and API client helpers."""

import os
from collections.abc import Iterator
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.main import create_app
from helpers import OpenClient
from support import truncate_application_tables, without_ambient_settings

# HTTPS, so cookies marked Secure are stored and sent back like a browser would.
API_BASE_URL = "https://testserver"


@pytest.fixture(autouse=True)
def isolated_integration_test(monkeypatch: pytest.MonkeyPatch, test_database_url: str) -> Iterator[None]:
    """Hide ambient CLOUDCART_* settings, then empty application tables after the test.

    Cleanup does not depend on the `database` fixture, so tests that only use
    `test_database_url` (independent connections, subprocesses) are covered too.
    """
    for name in os.environ.keys() - without_ambient_settings(os.environ).keys():
        monkeypatch.delenv(name)

    yield

    cleanup = Database(Settings(database_url=SecretStr(test_database_url)))
    try:
        with cleanup.engine.begin() as connection:
            truncate_application_tables(connection)
    finally:
        cleanup.dispose()


@pytest.fixture
def open_client(integration_settings: Settings) -> Iterator[OpenClient]:
    """Start API instances on the test database; each client is one browser with its own cookie jar.

    Call `open_client()` for another browser (or another API replica), optionally with
    different `settings` or starting `cookies`. Every instance shuts down after the test.
    """
    with ExitStack() as stack:

        def open_client(settings: Settings = integration_settings, cookies: dict[str, str] | None = None) -> TestClient:
            return stack.enter_context(TestClient(create_app(settings), base_url=API_BASE_URL, cookies=cookies))

        yield open_client
