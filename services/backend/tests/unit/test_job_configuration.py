"""Components that move orders refuse to start without a broker instead of silently never publishing."""

import os

import pytest
from pydantic import SecretStr

from cloudcart.config import ConfigurationError, Settings
from cloudcart.jobs import worker
from cloudcart.main import create_app

DATABASE_URL = "postgresql+psycopg://cloudcart:unit-test-only@127.0.0.1:5432/cloudcart"
BROKER_URL = "amqp://cloudcart:unit-test-only@127.0.0.1:5672//"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in list(os.environ):
        if name.startswith("CLOUDCART_"):
            monkeypatch.delenv(name)
    return monkeypatch


def test_api_requires_a_broker_url_while_its_publisher_is_enabled() -> None:
    with pytest.raises(ConfigurationError, match="CLOUDCART_BROKER_URL"):
        create_app(Settings(database_url=SecretStr(DATABASE_URL)))


def test_api_starts_without_a_broker_url_when_its_publisher_is_disabled() -> None:
    create_app(Settings(database_url=SecretStr(DATABASE_URL), publisher_enabled=False))
    create_app(Settings(database_url=SecretStr(DATABASE_URL), broker_url=SecretStr(BROKER_URL)))


def test_worker_requires_a_broker_url(isolated_environment: pytest.MonkeyPatch) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_PUBLISHER_ENABLED", "false")  # irrelevant to the worker

    with pytest.raises(ConfigurationError, match="CLOUDCART_BROKER_URL"):
        worker.main()
