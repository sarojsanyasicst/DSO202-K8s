"""Outbox publication against the disposable RabbitMQ: confirmed, persistent Celery task messages.

An event is marked published only after the broker confirms a routable message.
Publishers claim events with row locks that other publishers skip, plus a lease
that outlives a crash. Broker faults come from a loopback TCP proxy
(tests/faults.py), so outages are deterministic and stay inside the test.
"""

import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from uuid import UUID

import pytest
from kombu import Connection
from pydantic import SecretStr
from sqlalchemy import text

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.jobs.celery_app import orders_queue
from cloudcart.jobs.publisher import OrderPublisher, OutboxPublisher, PublishError, publish_batch
from faults import TcpProxy
from helpers import OpenClient, run_sql, start_guest
from jobs_support import (
    PlacedOrder,
    WorkerProcess,
    add_product,
    order_state,
    orders_queue_state,
    place_order,
    stock_of,
    take_queued_messages,
    wait_until,
)

BROKER_TIMEOUT_SECONDS = 1
FULFILL_TASK = "cloudcart.orders.fulfill"


@pytest.fixture
def publisher(broker_url: str) -> Iterator[OrderPublisher]:
    with closing(OrderPublisher(broker_url, timeout_seconds=BROKER_TIMEOUT_SECONDS)) as publisher:
        yield publisher


def unpublished_events(database: Database) -> list[UUID]:
    return [event_id for (event_id,) in run_sql(database, "SELECT id FROM outbox_events WHERE published_at IS NULL")]


def claimed_events(database: Database) -> list[UUID]:
    return [
        event_id for (event_id,) in run_sql(database, "SELECT id FROM outbox_events WHERE claimed_until IS NOT NULL")
    ]


def queued_event_ids(broker_url: str) -> list[str]:
    return sorted(message.headers["id"] for message in take_queued_messages(broker_url))


def publisher_settings(settings: Settings, broker_url: str, **overrides: object) -> Settings:
    return settings.model_copy(
        update={
            "publisher_enabled": True,
            "broker_url": SecretStr(broker_url),
            "broker_timeout_seconds": BROKER_TIMEOUT_SECONDS,
            "publisher_interval_ms": 100,
            **overrides,
        }
    )


def test_each_event_becomes_one_persistent_celery_task_message_and_is_then_marked_published(
    database: Database, broker_url: str, publisher: OrderPublisher
) -> None:
    first, second = place_order(database), place_order(database)
    before = datetime.now(UTC)

    assert publish_batch(database.session_factory, publisher) == 2

    after = datetime.now(UTC)
    messages = {message.headers["id"]: message for message in take_queued_messages(broker_url)}
    assert sorted(messages) == sorted([str(first.event_id), str(second.event_id)])
    for placed in (first, second):
        message = messages[str(placed.event_id)]
        assert message.headers["task"] == FULFILL_TASK
        assert message.content_type == "application/json"
        assert message.properties["delivery_mode"] == 2  # persistent
        args, kwargs, _ = message.payload
        assert kwargs == {}
        assert args[0] == str(placed.order_id)
        assert before <= datetime.fromisoformat(args[1]) <= after
    assert unpublished_events(database) == []
    assert claimed_events(database) == []

    assert publish_batch(database.session_factory, publisher) == 0
    assert take_queued_messages(broker_url) == []


def test_a_batch_publishes_at_most_its_limit_oldest_first(
    database: Database, broker_url: str, publisher: OrderPublisher
) -> None:
    placed = [place_order(database) for _ in range(3)]

    assert publish_batch(database.session_factory, publisher, limit=2) == 2
    assert queued_event_ids(broker_url) == sorted(str(order.event_id) for order in placed[:2])
    assert unpublished_events(database) == [placed[2].event_id]

    assert publish_batch(database.session_factory, publisher, limit=2) == 1
    assert queued_event_ids(broker_url) == [str(placed[2].event_id)]


def test_events_stay_unpublished_while_the_broker_refuses_connections_and_publish_after_recovery(
    database: Database, broker_url: str, proxy: Callable[[str], TcpProxy]
) -> None:
    broker = proxy(broker_url)
    broker.cut()
    placed = place_order(database)

    with closing(OrderPublisher(broker.url_for(broker_url), timeout_seconds=BROKER_TIMEOUT_SECONDS)) as publisher:
        with pytest.raises(PublishError):
            publish_batch(database.session_factory, publisher)

        assert unpublished_events(database) == [placed.event_id]
        assert claimed_events(database) == []  # released for any publisher to retry
        assert take_queued_messages(broker_url) == []

        broker.restore()
        assert publish_batch(database.session_factory, publisher) == 1

    assert unpublished_events(database) == []
    assert queued_event_ids(broker_url) == [str(placed.event_id)]


def test_a_stalled_broker_fails_each_publish_within_the_broker_timeout(
    database: Database, broker_url: str, proxy: Callable[[str], TcpProxy]
) -> None:
    broker = proxy(broker_url)
    with closing(OrderPublisher(broker.url_for(broker_url), timeout_seconds=BROKER_TIMEOUT_SECONDS)) as publisher:
        connected = place_order(database)
        assert publish_batch(database.session_factory, publisher) == 1

        broker.stall()  # the open connection stops answering: no confirm arrives
        waiting = place_order(database)
        started = time.monotonic()
        with pytest.raises(PublishError):
            publish_batch(database.session_factory, publisher)
        assert time.monotonic() - started < 3 * BROKER_TIMEOUT_SECONDS

        started = time.monotonic()  # a new connection's handshake gets no answer either
        with pytest.raises(PublishError):
            publish_batch(database.session_factory, publisher)
        assert time.monotonic() - started < 3 * BROKER_TIMEOUT_SECONDS
        assert unpublished_events(database) == [waiting.event_id]

        broker.restore()
        assert publish_batch(database.session_factory, publisher) == 1

    assert unpublished_events(database) == []
    # The unconfirmed send may or may not have reached the queue; the confirmed one did.
    assert str(waiting.event_id) in queued_event_ids(broker_url)
    assert connected.event_id not in unpublished_events(database)


def test_an_unroutable_message_is_not_marked_published(
    database: Database, broker_url: str, publisher: OrderPublisher
) -> None:
    place_order(database)
    assert publish_batch(database.session_factory, publisher) == 1  # declares the queue on this connection
    with Connection(broker_url, connect_timeout=5) as connection:
        orders_queue()(connection.default_channel).delete()  # its binding goes with it
    unroutable = place_order(database)

    with pytest.raises(PublishError):
        publish_batch(database.session_factory, publisher)

    assert unpublished_events(database) == [unroutable.event_id]
    assert publish_batch(database.session_factory, publisher) == 1  # a fresh connection declares the queue again
    assert queued_event_ids(broker_url) == [str(unroutable.event_id)]


def test_two_publishers_running_together_publish_each_event_exactly_once(database: Database, broker_url: str) -> None:
    product_id = add_product(database, stock=40)
    placed = [place_order(database, product_id, quantity=1) for _ in range(40)]

    def drain(publisher: OrderPublisher) -> int:
        published = 0
        while batch := publish_batch(database.session_factory, publisher, limit=3):
            published += batch
        return published

    with (
        closing(OrderPublisher(broker_url, timeout_seconds=BROKER_TIMEOUT_SECONDS)) as first,
        closing(OrderPublisher(broker_url, timeout_seconds=BROKER_TIMEOUT_SECONDS)) as second,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        totals = [future.result(timeout=30) for future in [pool.submit(drain, first), pool.submit(drain, second)]]

    assert sum(totals) == 40
    assert queued_event_ids(broker_url) == sorted(str(order.event_id) for order in placed)
    assert unpublished_events(database) == []


def test_a_publisher_skips_events_another_publisher_is_claiming_instead_of_waiting(
    database: Database, broker_url: str, publisher: OrderPublisher
) -> None:
    claimed, free = place_order(database), place_order(database)
    other = database.session_factory()
    try:
        other.execute(text("SELECT id FROM outbox_events WHERE id = :id FOR UPDATE"), {"id": claimed.event_id})
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(publish_batch, database.session_factory, publisher).result(timeout=5) == 1
    finally:
        other.rollback()
        other.close()

    assert queued_event_ids(broker_url) == [str(free.event_id)]
    assert publish_batch(database.session_factory, publisher) == 1
    assert queued_event_ids(broker_url) == [str(claimed.event_id)]


def test_live_claims_are_left_to_their_publisher_and_expired_claims_are_taken_over(
    database: Database, broker_url: str, publisher: OrderPublisher
) -> None:
    live, expired = place_order(database), place_order(database)
    run_sql(
        database,
        "UPDATE outbox_events SET claimed_until = now() + interval '1 minute' WHERE id = :id",
        id=live.event_id,
    )
    run_sql(
        database,
        "UPDATE outbox_events SET claimed_until = now() - interval '1 second' WHERE id = :id",
        id=expired.event_id,
    )

    assert publish_batch(database.session_factory, publisher) == 1

    assert queued_event_ids(broker_url) == [str(expired.event_id)]
    assert unpublished_events(database) == [live.event_id]


class SimulatedCrash(BaseException):
    """Stands in for the publisher process dying: no cleanup code runs for it."""


class CrashAfterConfirmation:
    """Publishes for real, then 'dies' before the event can be marked published."""

    def __init__(self, publisher: OrderPublisher) -> None:
        self.publisher = publisher

    def publish_order(self, order_id: UUID, event_id: UUID, enqueued_at: datetime) -> None:
        self.publisher.publish_order(order_id, event_id, enqueued_at)
        raise SimulatedCrash


def test_a_publisher_crash_after_confirmation_republishes_and_still_fulfils_the_order_once(
    database: Database,
    broker_url: str,
    publisher: OrderPublisher,
    start_worker: Callable[..., WorkerProcess],
) -> None:
    placed: PlacedOrder = place_order(database, quantity=2, stock=5)

    with pytest.raises(SimulatedCrash):
        publish_batch(database.session_factory, CrashAfterConfirmation(publisher))  # type: ignore[arg-type]

    assert orders_queue_state(broker_url)[0] == 1  # the broker confirmed the message
    assert unpublished_events(database) == [placed.event_id]
    assert claimed_events(database) == [placed.event_id]  # the dead publisher's lease is still running
    assert publish_batch(database.session_factory, publisher) == 0

    run_sql(database, "UPDATE outbox_events SET claimed_until = now() - interval '1 second'")  # the lease runs out
    assert publish_batch(database.session_factory, publisher) == 1
    assert orders_queue_state(broker_url)[0] == 2  # one event, delivered twice

    worker = start_worker()
    wait_until(lambda: orders_queue_state(broker_url)[0] == 0, "the worker takes both deliveries")
    assert worker.terminate() == 0  # a warm shutdown finishes and acknowledges the task in progress

    status, _, receipts = order_state(database, placed.order_id)
    assert (status, receipts) == ("fulfilled", 1)
    assert stock_of(database, placed.product_id) == 3  # charged once at checkout, never again
    assert orders_queue_state(broker_url) == (0, 0)


def test_the_api_serves_reads_and_checkout_while_the_broker_hangs_and_publishes_after_recovery(
    open_client: OpenClient,
    integration_settings: Settings,
    database: Database,
    broker_url: str,
    proxy: Callable[[str], TcpProxy],
) -> None:
    broker = proxy(broker_url)
    broker.stall()
    product_id = add_product(database, stock=5)
    client = open_client(publisher_settings(integration_settings, broker.url_for(broker_url)))
    shopper = start_guest(client)

    started = time.monotonic()
    assert client.get("/api/v1/products").status_code == 200
    cart = shopper.send("PUT", f"/api/v1/cart/items/{product_id}", {"quantity": 1}, shopper.csrf_token)
    assert cart.status_code == 200
    placed = shopper.send(
        "POST",
        "/api/v1/orders",
        {"cart_version": cart.json()["version"], "payment_outcome": "approved"},
        shopper.csrf_token,
        **{"Idempotency-Key": "broker-outage-0001"},
    )
    assert placed.status_code == 201, placed.text
    assert time.monotonic() - started < 2 * BROKER_TIMEOUT_SECONDS
    order_url = f"/api/v1/orders/{placed.json()['id']}"
    assert placed.json()["publication_pending"] is True

    time.sleep(3 * BROKER_TIMEOUT_SECONDS)  # several publish attempts fail meanwhile
    assert shopper.send("GET", order_url).json()["publication_pending"] is True
    assert take_queued_messages(broker_url) == []

    broker.restore()
    wait_until(lambda: shopper.send("GET", order_url).json()["publication_pending"] is False, "the order is published")
    [message] = take_queued_messages(broker_url)
    assert message.payload[0][0] == placed.json()["id"]


def test_the_publisher_backs_off_exponentially_while_the_broker_is_down(
    database: Database, integration_settings: Settings, broker_url: str, proxy: Callable[[str], TcpProxy]
) -> None:
    broker = proxy(broker_url)
    broker.cut()
    place_order(database)
    publisher = OutboxPublisher(
        database.session_factory, publisher_settings(integration_settings, broker.url_for(broker_url))
    )

    publisher.start()
    time.sleep(3)
    publisher.stop()

    # Waits of 0.1, 0.2, 0.4, 0.8, 1.6 s allow about five attempts in 3 s; a fixed 0.1 s interval would allow 30.
    assert 3 <= broker.accepted <= 6
    assert not publisher.is_alive()


def test_stopping_the_publisher_interrupts_its_wait(
    database: Database, integration_settings: Settings, broker_url: str
) -> None:
    publisher = OutboxPublisher(
        database.session_factory, publisher_settings(integration_settings, broker_url, publisher_interval_ms=60_000)
    )
    publisher.start()
    time.sleep(0.5)  # now inside its 60 s idle wait

    started = time.monotonic()
    publisher.stop()

    assert time.monotonic() - started < 1
    assert not publisher.is_alive()
