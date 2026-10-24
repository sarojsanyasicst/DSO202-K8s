"""Concurrent checkouts on independent PostgreSQL connections: no overselling, one order per idempotency key.

The service-level tests hold the first transaction open, wait until PostgreSQL
reports the second one blocked by the first, and only then commit the first, so
the overlap is certain rather than a matter of thread timing. The HTTP tests race
whole requests from several API instances, each with its own connection pool.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from httpx2 import Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from cloudcart.cart.service import set_cart_item
from cloudcart.db import Database
from cloudcart.identity.security import ensure_guest
from cloudcart.orders.service import InsufficientStockError, checkout
from cloudcart.seed import seed_database
from helpers import LOCK_WAIT_TIMEOUT_SECONDS, Browser, OpenClient, backend_pid, run_sql, start_guest, wait_until_blocked

# TEST-ONLY instructor password.
ADMIN_PASSWORD = "concurrency-test-instructor-password"


@pytest.fixture
def last_unit(database: Database) -> UUID:
    """A seeded product with exactly one unit left."""
    with database.session_scope() as session:
        seed_database(session, ADMIN_PASSWORD)
    [(product_id,)] = run_sql(database, "UPDATE products SET stock = 1 WHERE sku = 'kube-mug' RETURNING id")
    return product_id


@pytest.fixture
def two_sessions(database: Database) -> Iterator[tuple[Session, Session]]:
    """Two sessions on two independent connections."""
    first, second = database.session_factory(), database.session_factory()
    try:
        yield first, second
    finally:
        first.close()
        second.close()


def guest_with_cart(database: Database, product_id: UUID) -> tuple[UUID, int]:
    """A new guest whose cart holds one unit of `product_id`; returns the guest id and cart version."""
    with database.session_scope() as session:
        guest = ensure_guest(session, None)
        cart = set_cart_item(session, guest.guest_id, product_id, 1)
    return guest.guest_id, cart.version


def durable_counts(database: Database, product_id: UUID) -> tuple:
    return (
        run_sql(database, "SELECT stock FROM products WHERE id = :id", id=product_id)[0][0],
        run_sql(database, "SELECT count(*) FROM orders")[0][0],
        run_sql(database, "SELECT count(*) FROM outbox_events")[0][0],
    )


def test_second_checkout_waits_for_the_first_and_cannot_oversell_the_last_unit(
    database: Database, last_unit: UUID, two_sessions: tuple[Session, Session]
) -> None:
    first, second = two_sessions
    alice, alice_version = guest_with_cart(database, last_unit)
    bob, bob_version = guest_with_cart(database, last_unit)
    first_pid, second_pid = backend_pid(first), backend_pid(second)

    accepted = checkout(first, alice, alice_version, "approved", "alice-key-0001")  # uncommitted
    with ThreadPoolExecutor(max_workers=1) as pool:
        racing = pool.submit(checkout, second, bob, bob_version, "approved", "bob-key-0001")
        wait_until_blocked(database, second_pid, by=first_pid)
        first.commit()
        with pytest.raises(InsufficientStockError):
            racing.result(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
    second.rollback()

    assert accepted.replayed is False
    assert durable_counts(database, last_unit) == (0, 1, 1)
    assert run_sql(database, "SELECT id, guest_id FROM orders") == [(accepted.order.id, alice)]


def test_simultaneous_retries_with_one_key_create_one_order(
    database: Database, last_unit: UUID, two_sessions: tuple[Session, Session]
) -> None:
    first, second = two_sessions
    guest, version = guest_with_cart(database, last_unit)
    first_pid, second_pid = backend_pid(first), backend_pid(second)

    original = checkout(first, guest, version, "approved", "same-key-0001")  # uncommitted
    with ThreadPoolExecutor(max_workers=1) as pool:
        retry = pool.submit(checkout, second, guest, version, "approved", "same-key-0001")
        wait_until_blocked(database, second_pid, by=first_pid)
        first.commit()
        replay = retry.result(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
    second.commit()

    assert (original.replayed, replay.replayed) == (False, True)
    assert replay.order.id == original.order.id
    assert durable_counts(database, last_unit) == (0, 1, 1)


def test_checkout_locks_products_in_id_order_whatever_the_cart_order(
    database: Database, last_unit: UUID, two_sessions: tuple[Session, Session]
) -> None:
    """Every checkout takes product locks in the same order, so two multi-product checkouts cannot deadlock."""
    holder, buyer = two_sessions
    low, high = sorted(product_id for (product_id,) in run_sql(database, "SELECT id FROM products LIMIT 2"))
    with database.session_scope() as session:
        guest = ensure_guest(session, None)
        set_cart_item(session, guest.guest_id, high, 1)  # added first, but locked last
        cart = set_cart_item(session, guest.guest_id, low, 1)
    holder_pid, buyer_pid = backend_pid(holder), backend_pid(buyer)
    holder.execute(text("SELECT id FROM products WHERE id = :id FOR UPDATE"), {"id": high})
    probe = database.session_factory()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            buying = pool.submit(checkout, buyer, guest.guest_id, cart.version, "approved", "ordered-key-0001")
            try:
                wait_until_blocked(database, buyer_pid, by=holder_pid)
                # While it waits for the higher id, the checkout already holds the lower one.
                with pytest.raises(OperationalError, match="could not obtain lock"):
                    probe.execute(text("SELECT id FROM products WHERE id = :id FOR NO KEY UPDATE NOWAIT"), {"id": low})
            finally:
                holder.rollback()
            placed = buying.result(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
        buyer.commit()
    finally:
        probe.close()

    assert placed.replayed is False
    assert {item.product_id for item in placed.order.items} == {low, high}


def race(requests: list[Callable[[], Response]]) -> list[Response]:
    """Run the callables at the same moment, one thread each; return their results in order."""
    barrier = threading.Barrier(len(requests))

    def run(request: Callable[[], Response]) -> Response:
        barrier.wait(timeout=LOCK_WAIT_TIMEOUT_SECONDS)
        return request()

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(run, requests))


def http_checkout(browser: Browser, product_id: UUID, key: str) -> Callable[[], Response]:
    """Fill the guest's cart with one unit; return the checkout request, ready to send."""
    response = browser.send("PUT", f"/api/v1/cart/items/{product_id}", {"quantity": 1}, browser.csrf_token)
    assert response.status_code == 200, response.text
    body = {"cart_version": response.json()["version"], "payment_outcome": "approved"}
    return lambda: browser.send("POST", "/api/v1/orders", body, browser.csrf_token, **{"Idempotency-Key": key})


@pytest.mark.parametrize("racers", [2, 6])
def test_guests_racing_for_the_last_unit_over_http_get_exactly_one_order(
    open_client: OpenClient, database: Database, last_unit: UUID, racers: int
) -> None:
    # One API instance (engine and connection pool) per guest.
    requests = [http_checkout(start_guest(open_client()), last_unit, f"race-{uuid4()}") for _ in range(racers)]

    responses = race(requests)

    assert sorted(response.status_code for response in responses) == [201] + [409] * (racers - 1)
    for response in responses:
        if response.status_code == 409:
            assert "stock" in response.json()["detail"].lower()
    assert durable_counts(database, last_unit) == (0, 1, 1)


def test_simultaneous_same_key_requests_over_http_return_one_order(
    open_client: OpenClient, database: Database, last_unit: UUID
) -> None:
    request = http_checkout(start_guest(open_client()), last_unit, f"retry-{uuid4()}")

    responses = race([request] * 5)

    assert sorted(response.status_code for response in responses) == [200] * 4 + [201]
    assert len({response.json()["id"] for response in responses}) == 1
    assert durable_counts(database, last_unit) == (0, 1, 1)
