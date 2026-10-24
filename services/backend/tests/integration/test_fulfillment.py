"""Idempotent fulfillment: one receipt and one final transition per order, however often its task runs.

Service tests overlap two transactions on independent connections. Worker tests
run real `cloudcart.jobs.worker` subprocesses (through tests/worker_harness.py,
which adds test-only dispatch failures and crashes) against the disposable
PostgreSQL and RabbitMQ, and judge the outcome from PostgreSQL rather than from
task return values.
"""

import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from cloudcart.cart.service import set_cart_item
from cloudcart.db import Database
from cloudcart.identity.security import ensure_guest
from cloudcart.jobs.publisher import OrderPublisher, publish_batch
from cloudcart.jobs.tasks import MAX_FULFILLMENT_ATTEMPTS, begin_attempt, fail_order, fulfill_order
from cloudcart.orders.service import checkout
from faults import TcpProxy
from helpers import LOCK_WAIT_TIMEOUT_SECONDS, backend_pid, run_sql, wait_until_blocked
from jobs_support import WorkerProcess, add_product, order_state, orders_queue_state, place_order, stock_of, wait_until


@pytest.fixture
def two_sessions(database: Database) -> Iterator[tuple[Session, Session]]:
    first, second = database.session_factory(), database.session_factory()
    try:
        yield first, second
    finally:
        first.close()
        second.close()


@pytest.fixture
def publisher(broker_url: str) -> Iterator[OrderPublisher]:
    with closing(OrderPublisher(broker_url, timeout_seconds=2)) as publisher:
        yield publisher


def failure_reason(database: Database, order_id: object) -> str | None:
    return run_sql(database, "SELECT failure_reason FROM orders WHERE id = :id", id=order_id)[0][0]


# Service level: the transitions themselves.


def test_fulfilling_an_order_issues_one_receipt_and_marks_it_fulfilled(database: Database) -> None:
    placed = place_order(database, quantity=2, stock=5)

    with database.session_scope() as session:
        result = fulfill_order(session, placed.order_id)

    assert (result.order_id, result.status, result.already_applied) == (placed.order_id, "fulfilled", False)
    assert run_sql(database, "SELECT id, order_id FROM receipts") == [(result.receipt_id, placed.order_id)]
    assert order_state(database, placed.order_id) == ("fulfilled", 0, 1)
    assert stock_of(database, placed.product_id) == 3  # charged at checkout only


def test_fulfilling_again_is_already_applied_and_changes_nothing(database: Database) -> None:
    placed = place_order(database)
    with database.session_scope() as session:
        first = fulfill_order(session, placed.order_id)

    with database.session_scope() as session:
        again = fulfill_order(session, placed.order_id)

    assert (again.status, again.receipt_id, again.already_applied) == ("fulfilled", first.receipt_id, True)
    assert run_sql(database, "SELECT count(*) FROM receipts") == [(1,)]


def test_concurrent_fulfillment_waits_for_the_first_and_issues_one_receipt(
    database: Database, two_sessions: tuple[Session, Session]
) -> None:
    first, second = two_sessions
    placed = place_order(database)
    first_pid, second_pid = backend_pid(first), backend_pid(second)

    original = fulfill_order(first, placed.order_id)  # uncommitted: holds the order row
    with ThreadPoolExecutor(max_workers=1) as pool:
        duplicate = pool.submit(fulfill_order, second, placed.order_id)
        wait_until_blocked(database, second_pid, by=first_pid)
        first.commit()
        repeated = duplicate.result(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
    second.commit()

    assert (original.already_applied, repeated.already_applied) == (False, True)
    assert repeated.receipt_id == original.receipt_id
    assert run_sql(database, "SELECT count(*) FROM receipts") == [(1,)]


def test_failing_an_order_returns_its_reserved_stock_once_and_keeps_a_failure_record(database: Database) -> None:
    placed = place_order(database, quantity=2, stock=5)

    with database.session_scope() as session:
        failed = fail_order(session, placed.order_id, "Dispatch failed on every attempt.")
    with database.session_scope() as session:
        again = fail_order(session, placed.order_id, "A duplicate delivery gave up too.")
    with database.session_scope() as session:
        late_success = fulfill_order(session, placed.order_id)

    assert (failed.status, failed.receipt_id, failed.already_applied) == ("failed", None, False)
    assert (again.status, again.already_applied) == ("failed", True)
    assert (late_success.status, late_success.receipt_id, late_success.already_applied) == ("failed", None, True)
    assert stock_of(database, placed.product_id) == 5
    assert order_state(database, placed.order_id) == ("failed", 0, 0)
    assert failure_reason(database, placed.order_id) == "Dispatch failed on every attempt."


def test_concurrent_failures_return_the_stock_once(database: Database, two_sessions: tuple[Session, Session]) -> None:
    first, second = two_sessions
    placed = place_order(database, quantity=3, stock=4)
    first_pid, second_pid = backend_pid(first), backend_pid(second)

    fail_order(first, placed.order_id, "first")
    with ThreadPoolExecutor(max_workers=1) as pool:
        duplicate = pool.submit(fail_order, second, placed.order_id, "second")
        wait_until_blocked(database, second_pid, by=first_pid)
        first.commit()
        repeated = duplicate.result(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
    second.commit()

    assert repeated.already_applied is True
    assert stock_of(database, placed.product_id) == 4
    assert failure_reason(database, placed.order_id) == "first"


def test_a_fulfilled_order_never_fails_or_returns_stock(database: Database) -> None:
    placed = place_order(database, quantity=2, stock=5)
    with database.session_scope() as session:
        fulfilled = fulfill_order(session, placed.order_id)

    with database.session_scope() as session:
        late_failure = fail_order(session, placed.order_id, "too late")

    assert (late_failure.status, late_failure.receipt_id, late_failure.already_applied) == (
        "fulfilled",
        fulfilled.receipt_id,
        True,
    )
    assert stock_of(database, placed.product_id) == 3
    assert failure_reason(database, placed.order_id) is None


def test_failing_a_multi_product_order_returns_every_line(database: Database) -> None:
    mug, cap = add_product(database, stock=5), add_product(database, stock=2)
    with database.session_scope() as session:
        guest = ensure_guest(session, None)
        set_cart_item(session, guest.guest_id, mug, 2)
        cart = set_cart_item(session, guest.guest_id, cap, 1)
        order = checkout(session, guest.guest_id, cart.version, "approved", "multi-line-0001").order
    assert (stock_of(database, mug), stock_of(database, cap)) == (3, 1)

    with database.session_scope() as session:
        fail_order(session, order.id, "failed")

    assert (stock_of(database, mug), stock_of(database, cap)) == (5, 2)


def test_returning_stock_locks_products_in_id_order_like_checkout(
    database: Database, two_sessions: tuple[Session, Session]
) -> None:
    """The same lock order as checkout (D025), so a failure and a checkout cannot deadlock."""
    holder, failing = two_sessions
    low, high = sorted([add_product(database, stock=5), add_product(database, stock=5)])
    with database.session_scope() as session:
        guest = ensure_guest(session, None)
        set_cart_item(session, guest.guest_id, high, 1)
        cart = set_cart_item(session, guest.guest_id, low, 1)
        order = checkout(session, guest.guest_id, cart.version, "approved", "lock-order-0001").order
    holder_pid, failing_pid = backend_pid(holder), backend_pid(failing)
    holder.execute(text("SELECT id FROM products WHERE id = :id FOR UPDATE"), {"id": high})
    probe = database.session_factory()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            returning = pool.submit(fail_order, failing, order.id, "failed")
            try:
                wait_until_blocked(database, failing_pid, by=holder_pid)
                # While it waits for the higher id, it already holds the lower one.
                with pytest.raises(OperationalError, match="could not obtain lock"):
                    probe.execute(text("SELECT id FROM products WHERE id = :id FOR NO KEY UPDATE NOWAIT"), {"id": low})
            finally:
                holder.rollback()
            returning.result(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
        failing.commit()
    finally:
        probe.close()

    assert (stock_of(database, low), stock_of(database, high)) == (5, 5)


def test_attempts_are_counted_in_postgresql_and_stop_at_the_limit(database: Database) -> None:
    placed = place_order(database)

    started = []
    for _ in range(MAX_FULFILLMENT_ATTEMPTS + 1):
        with database.session_scope() as session:
            started.append(begin_attempt(session, placed.order_id))

    assert [attempt.number for attempt in started] == [1, 2, 3, 4, None]
    assert {attempt.order_status for attempt in started} == {"processing"}
    assert order_state(database, placed.order_id) == ("processing", 4, 0)

    with database.session_scope() as session:
        fulfill_order(session, placed.order_id)
        finished = begin_attempt(session, placed.order_id)
    assert (finished.order_status, finished.number) == ("fulfilled", None)
    assert order_state(database, placed.order_id) == ("fulfilled", 4, 1)


# Worker level: real deliveries through RabbitMQ.


def publish(database: Database, publisher: OrderPublisher) -> None:
    assert publish_batch(database.session_factory, publisher) >= 1


def test_the_worker_shows_processing_then_fulfils_a_published_order(
    database: Database, broker_url: str, publisher: OrderPublisher, start_worker: Callable[..., WorkerProcess]
) -> None:
    placed = place_order(database, quantity=2, stock=5)
    start_worker(fulfillment_delay_ms=1500)

    publish(database, publisher)

    wait_until(lambda: order_state(database, placed.order_id) == ("processing", 1, 0), "the order is processing")
    wait_until(lambda: order_state(database, placed.order_id)[0] == "fulfilled", "the order is fulfilled")
    assert order_state(database, placed.order_id) == ("fulfilled", 1, 1)
    assert stock_of(database, placed.product_id) == 3
    assert orders_queue_state(broker_url)[0] == 0


def test_the_worker_acknowledges_a_task_for_an_unknown_order(
    broker_url: str, publisher: OrderPublisher, start_worker: Callable[..., WorkerProcess]
) -> None:
    worker = start_worker()

    publisher.publish_order(uuid4(), uuid4(), datetime.now(UTC))

    wait_until(lambda: orders_queue_state(broker_url)[0] == 0, "the worker takes the task")
    assert worker.terminate() == 0
    assert orders_queue_state(broker_url) == (0, 0)  # acknowledged, not requeued


def test_duplicate_deliveries_to_two_workers_issue_one_receipt(
    database: Database, publisher: OrderPublisher, start_worker: Callable[..., WorkerProcess]
) -> None:
    placed = place_order(database, quantity=2, stock=5)
    start_worker(fulfillment_delay_ms=1000)
    start_worker(fulfillment_delay_ms=1000)

    enqueued_at = datetime.now(UTC)
    publisher.publish_order(placed.order_id, placed.event_id, enqueued_at)
    publisher.publish_order(placed.order_id, placed.event_id, enqueued_at)  # e.g. republished after a crash

    wait_until(lambda: order_state(database, placed.order_id) == ("fulfilled", 2, 1), "both deliveries ran")
    time.sleep(1.5)  # long enough for a second fulfillment to show up
    assert order_state(database, placed.order_id) == ("fulfilled", 2, 1)
    assert stock_of(database, placed.product_id) == 3


def test_a_worker_killed_after_its_commit_gets_the_task_redelivered_without_a_second_fulfillment(
    database: Database,
    broker_url: str,
    publisher: OrderPublisher,
    start_worker: Callable[..., WorkerProcess],
) -> None:
    placed = place_order(database, quantity=2, stock=5)
    crashing = start_worker(test_crash_after_task=1)

    publish(database, publisher)

    wait_until(lambda: crashing.process.poll() is not None, "the worker kills itself after the task")
    assert order_state(database, placed.order_id) == ("fulfilled", 1, 1)
    wait_until(lambda: orders_queue_state(broker_url) == (1, 0), "RabbitMQ requeues the unacknowledged task")

    replacement = start_worker()
    wait_until(lambda: orders_queue_state(broker_url)[0] == 0, "the replacement worker takes the task")
    assert replacement.terminate() == 0

    assert order_state(database, placed.order_id) == ("fulfilled", 1, 1)
    assert stock_of(database, placed.product_id) == 3
    assert orders_queue_state(broker_url) == (0, 0)


def test_transient_failures_are_retried_with_backoff_and_keep_the_stock_reserved(
    database: Database, publisher: OrderPublisher, start_worker: Callable[..., WorkerProcess]
) -> None:
    placed = place_order(database, quantity=2, stock=5)
    start_worker(test_failing_attempts=2, fulfillment_retry_backoff_ms=300)

    started = time.monotonic()
    publish(database, publisher)

    def fulfilled_with_stock_reserved() -> bool:
        assert stock_of(database, placed.product_id) == 3, "stock was released before the retries ended"
        return order_state(database, placed.order_id)[0] == "fulfilled"

    wait_until(fulfilled_with_stock_reserved, "a retry succeeds")
    assert time.monotonic() - started >= 0.3 + 0.6  # backoff after attempts 1 and 2
    assert order_state(database, placed.order_id) == ("fulfilled", 3, 1)
    assert failure_reason(database, placed.order_id) is None


def test_exhausted_retries_fail_the_order_once_and_return_its_stock(
    database: Database,
    broker_url: str,
    publisher: OrderPublisher,
    start_worker: Callable[..., WorkerProcess],
) -> None:
    placed = place_order(database, quantity=2, stock=5)
    worker = start_worker(test_failing_attempts=MAX_FULFILLMENT_ATTEMPTS)

    publish(database, publisher)

    wait_until(lambda: order_state(database, placed.order_id)[0] == "failed", "the retries are exhausted")
    assert order_state(database, placed.order_id) == ("failed", MAX_FULFILLMENT_ATTEMPTS, 0)
    assert stock_of(database, placed.product_id) == 5
    assert failure_reason(database, placed.order_id) is not None

    publisher.publish_order(placed.order_id, placed.event_id, datetime.now(UTC))  # a late duplicate delivery
    wait_until(lambda: orders_queue_state(broker_url)[0] == 0, "the worker takes the duplicate")
    assert worker.terminate() == 0

    assert order_state(database, placed.order_id) == ("failed", MAX_FULFILLMENT_ATTEMPTS, 0)
    assert stock_of(database, placed.product_id) == 5
    assert orders_queue_state(broker_url) == (0, 0)


def test_sigterm_during_a_task_lets_it_finish_and_acknowledges_it(
    database: Database, broker_url: str, publisher: OrderPublisher, start_worker: Callable[..., WorkerProcess]
) -> None:
    placed = place_order(database)
    worker = start_worker(fulfillment_delay_ms=2000)
    publish(database, publisher)
    wait_until(lambda: order_state(database, placed.order_id)[0] == "processing", "the task is running")

    assert worker.terminate() == 0

    assert order_state(database, placed.order_id) == ("fulfilled", 1, 1)
    assert orders_queue_state(broker_url) == (0, 0)


def test_a_worker_ahead_of_the_schema_requeues_its_deliveries_until_the_migration_lands(
    database: Database, publisher: OrderPublisher, start_worker: Callable[..., WorkerProcess]
) -> None:
    """A database error that is not a lost connection (here UndefinedColumn) must not drop the task."""
    placed = place_order(database, quantity=2, stock=5)
    worker = start_worker()
    run_sql(database, "ALTER TABLE orders RENAME COLUMN fulfillment_attempts TO fulfillment_attempts_pending")
    try:
        publish(database, publisher)
        wait_until(lambda: "ProgrammingError" in worker.log(), "the worker hits the schema mismatch")
        time.sleep(0.5)  # a few more deliveries fail meanwhile
        assert run_sql(database, "SELECT status FROM orders WHERE id = :id", id=placed.order_id) == [("accepted",)]
    finally:
        run_sql(database, "ALTER TABLE orders RENAME COLUMN fulfillment_attempts_pending TO fulfillment_attempts")

    wait_until(lambda: order_state(database, placed.order_id)[0] == "fulfilled", "the requeued task succeeds")
    assert order_state(database, placed.order_id) == ("fulfilled", 1, 1)
    assert stock_of(database, placed.product_id) == 3


def test_an_idle_worker_stops_within_seconds_of_sigterm(
    broker_url: str, start_worker: Callable[..., WorkerProcess]
) -> None:
    worker = start_worker()
    time.sleep(1)  # idle in its event loop

    started = time.monotonic()
    assert worker.terminate() == 0

    assert time.monotonic() - started < 3
    assert orders_queue_state(broker_url)[1] == 0


def test_a_database_outage_delays_fulfillment_without_using_up_attempts(
    database: Database,
    test_database_url: str,
    publisher: OrderPublisher,
    proxy: Callable[[str], TcpProxy],
    start_worker: Callable[..., WorkerProcess],
) -> None:
    placed = place_order(database, quantity=2, stock=5)
    postgres = proxy(test_database_url)
    start_worker(database_url=postgres.url_for(test_database_url))
    postgres.cut()
    connections_before = postgres.accepted

    publish(database, publisher)

    wait_until(lambda: postgres.accepted >= connections_before + 3, "the worker retries the database")
    assert order_state(database, placed.order_id) == ("accepted", 0, 0)
    assert stock_of(database, placed.product_id) == 3

    postgres.restore()
    wait_until(lambda: order_state(database, placed.order_id)[0] == "fulfilled", "the order is fulfilled")
    assert order_state(database, placed.order_id) == ("fulfilled", 1, 1)
    assert stock_of(database, placed.product_id) == 3
