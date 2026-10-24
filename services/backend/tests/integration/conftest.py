"""Isolation applied to every integration test, whichever fixtures it requests, and API client helpers."""

import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.main import create_app
from faults import TcpProxy
from helpers import OpenClient
from jobs_support import WorkerProcess, orders_queue_state, purge_orders_queue, wait_until, worker_environment
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
def broker_url(test_broker_url: str) -> Iterator[str]:
    """The disposable broker, with the orders queue empty before and after the test."""
    purge_orders_queue(test_broker_url)
    yield test_broker_url
    purge_orders_queue(test_broker_url)


@pytest.fixture
def proxy() -> Iterator[Callable[[str], TcpProxy]]:
    """`proxy(url)` starts a fault-injecting TCP proxy in front of the dependency at `url`."""
    proxies: list[TcpProxy] = []

    def start(url: str) -> TcpProxy:
        proxies.append(TcpProxy.for_url(url))
        return proxies[-1]

    yield start
    for started in proxies:
        started.close()


@pytest.fixture
def start_worker(test_database_url: str, broker_url: str, tmp_path: Path) -> Iterator[Callable[..., WorkerProcess]]:
    """`start_worker(**settings)` starts a worker subprocess and waits until it consumes the orders queue.

    Keyword arguments become CLOUDCART_* variables (for example `fulfillment_delay_ms=0`,
    or the harness's `test_failing_attempts=2`); `database_url`/`broker_url` override the
    connection URLs. Every worker is stopped when the test ends.
    """
    workers: list[WorkerProcess] = []

    def start(database_url: str = test_database_url, broker: str = broker_url, **settings: object) -> WorkerProcess:
        settings = {"fulfillment_delay_ms": 0, "fulfillment_retry_backoff_ms": 50, **settings}
        consumers = orders_queue_state(broker_url)[1]
        worker = WorkerProcess(
            worker_environment(database_url, broker, **settings), tmp_path / f"worker-{len(workers) + 1}.log"
        )
        workers.append(worker)
        wait_until(
            lambda: orders_queue_state(broker_url)[1] > consumers or worker.process.poll() is not None,
            "the worker consumes the orders queue",
        )
        if worker.process.poll() is not None:
            pytest.fail(f"Worker exited with {worker.process.returncode}. Log:\n{worker.log()}", pytrace=False)
        return worker

    yield start
    for worker in workers:
        worker.stop()


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
