"""Isolation applied to every integration test, whichever fixtures it requests."""

import os
from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from cloudcart.config import Settings
from cloudcart.db import Database
from support import truncate_application_tables, without_ambient_settings


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
