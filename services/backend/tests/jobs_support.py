"""Helpers for outbox-publication and fulfillment tests: orders, the orders queue, and worker subprocesses."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from kombu import Connection
from kombu.message import Message

from cloudcart.cart.service import set_cart_item
from cloudcart.db import Database
from cloudcart.identity.security import ensure_guest
from cloudcart.jobs.celery_app import orders_queue
from cloudcart.orders.service import checkout
from helpers import run_sql
from support import without_ambient_settings

WORKER_HARNESS = Path(__file__).with_name("worker_harness.py")
WAIT_SECONDS = 20
WORKER_STOP_SECONDS = 15


@dataclass(frozen=True)
class PlacedOrder:
    order_id: UUID
    event_id: UUID
    product_id: UUID
    quantity: int


def add_product(database: Database, stock: int, price_cents: int = 1250) -> UUID:
    sku = f"test-{uuid4().hex[:12]}"
    [(product_id,)] = run_sql(
        database,
        "INSERT INTO products (id, sku, name, description, price_cents, currency, stock) "
        "VALUES (:id, :sku, :name, 'Test product', :price, 'USD', :stock) RETURNING id",
        id=uuid4(),
        sku=sku,
        name=f"Product {sku}",
        price=price_cents,
        stock=stock,
    )
    return product_id


def place_order(database: Database, product_id: UUID | None = None, quantity: int = 2, stock: int = 5) -> PlacedOrder:
    """Check out a new guest's cart through the real checkout service; the order is accepted and unpublished."""
    if product_id is None:
        product_id = add_product(database, stock=stock)
    with database.session_scope() as session:
        guest = ensure_guest(session, None)
        cart = set_cart_item(session, guest.guest_id, product_id, quantity)
        result = checkout(session, guest.guest_id, cart.version, "approved", f"jobs-{uuid4()}")
    [(event_id,)] = run_sql(database, "SELECT id FROM outbox_events WHERE order_id = :id", id=result.order.id)
    return PlacedOrder(result.order.id, event_id, product_id, quantity)


def stock_of(database: Database, product_id: UUID) -> int:
    return run_sql(database, "SELECT stock FROM products WHERE id = :id", id=product_id)[0][0]


def order_state(database: Database, order_id: UUID) -> tuple[str, int, int]:
    """(status, fulfillment attempts, receipts) straight from PostgreSQL."""
    return run_sql(
        database,
        "SELECT status, fulfillment_attempts, (SELECT count(*) FROM receipts WHERE order_id = orders.id) "
        "FROM orders WHERE id = :id",
        id=order_id,
    )[0]


def wait_until(condition: Callable[[], object], what: str, timeout: float = WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail(f"Timed out after {timeout} s waiting until {what}.", pytrace=False)
        time.sleep(0.05)


def purge_orders_queue(broker_url: str) -> None:
    with Connection(broker_url, connect_timeout=5) as connection:
        queue = orders_queue()(connection.default_channel)
        queue.declare()
        queue.purge()


def orders_queue_state(broker_url: str) -> tuple[int, int]:
    """(ready messages, consumers) of the orders queue, as RabbitMQ reports them."""
    with Connection(broker_url, connect_timeout=5) as connection:
        _, messages, consumers = connection.default_channel.queue_declare(orders_queue().name, passive=True)
    return messages, consumers


def take_queued_messages(broker_url: str) -> list[Message]:
    """Remove and return every ready message in the orders queue."""
    taken = []
    with Connection(broker_url, connect_timeout=5) as connection:
        queue = orders_queue()(connection.default_channel)
        while (message := queue.get(no_ack=True, accept=["json"])) is not None:
            taken.append(message)
    return taken


class WorkerProcess:
    """One `cloudcart.jobs.worker` subprocess, started through the test harness."""

    def __init__(self, environment: dict[str, str], log_path: Path) -> None:
        self.log_path = log_path
        with log_path.open("wb") as log:
            self.process = subprocess.Popen(
                [sys.executable, str(WORKER_HARNESS)], env=environment, stdout=log, stderr=subprocess.STDOUT
            )

    def log(self) -> str:
        return self.log_path.read_text(errors="replace")

    def terminate(self, timeout: float = WORKER_STOP_SECONDS) -> int:
        """SIGTERM (Celery warm shutdown) and wait; fail if the worker does not exit in time."""
        self.process.send_signal(signal.SIGTERM)
        try:
            return self.process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            pytest.fail(f"Worker ignored SIGTERM for {timeout} s. Log:\n{self.log()}", pytrace=False)

    def stop(self) -> None:
        """Best-effort cleanup that never fails the test."""
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(WORKER_STOP_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def worker_environment(database_url: str, broker_url: str, **settings: object) -> dict[str, str]:
    """Environment for a worker subprocess; `settings` become CLOUDCART_* variables (name upper-cased)."""
    environment = without_ambient_settings(os.environ)
    environment["CLOUDCART_DATABASE_URL"] = database_url
    environment["CLOUDCART_BROKER_URL"] = broker_url
    for name, value in settings.items():
        environment[f"CLOUDCART_{name.upper()}"] = str(value)
    return environment
