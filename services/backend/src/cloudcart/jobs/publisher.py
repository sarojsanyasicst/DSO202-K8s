"""Outbox publication: hands accepted orders to the fulfillment queue, at least once.

Each API process runs one `OutboxPublisher` thread. It claims a batch of
unpublished outbox events, publishes one Celery task message per event, and
marks an event published only after RabbitMQ confirms a persistent, routable
message. Nothing here holds a database transaction open while it talks to the
broker, so a slow or absent broker never blocks checkout.

Claims coordinate API replicas. The claim query skips rows another publisher is
claiming right now (`FOR UPDATE SKIP LOCKED`) and sets a lease (`claimed_until`)
that the other publishers respect. A publisher that dies after the broker
confirmed a message but before marking its event leaves the lease to run out;
another publisher then sends the event again. Fulfillment is idempotent, so that
duplicate delivery is harmless; the task ID (the event ID) is not a
deduplication guarantee.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import Celery
from kombu import Connection, Producer
from kombu.entity import PERSISTENT_DELIVERY_MODE
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from cloudcart.config import Settings
from cloudcart.jobs.celery_app import FULFILL_TASK, ORDERS_QUEUE, orders_queue
from cloudcart.orders.models import OutboxEvent

logger = logging.getLogger(__name__)

BATCH_LIMIT = 20
# After a publisher crash its claimed events wait this long before another
# publisher takes them over. A batch slowed down by a stalling broker can outlast
# the lease; another publisher may then send an event again, a duplicate the
# worker tolerates.
CLAIM_LEASE = timedelta(seconds=60)
MAX_BACKOFF_SECONDS = 30.0


class PublishError(Exception):
    """RabbitMQ did not confirm a routable message in time."""


class OrderPublisher:
    """Sends fulfillment tasks over one reusable broker connection, waiting for each publisher confirm.

    Every broker call is bounded by `timeout_seconds`. After any failure the connection is
    dropped, and the next publish opens a new one (and declares the queue again).
    """

    def __init__(self, broker_url: str, timeout_seconds: float) -> None:
        self._broker_url = broker_url
        self._timeout = timeout_seconds
        self._messages = Celery("cloudcart", set_as_current=False)  # builds Celery protocol messages only
        self._connection: Connection | None = None
        self._producer: Producer | None = None

    def publish_order(self, order_id: UUID, event_id: UUID, enqueued_at: datetime) -> None:
        """Publish `cloudcart.orders.fulfill(order_id, enqueued_at)` with task ID `event_id`; raise PublishError unless confirmed."""
        message = self._messages.amqp.as_task_v2(
            str(event_id), FULFILL_TASK, args=(str(order_id), enqueued_at.isoformat())
        )
        try:
            queue = orders_queue()
            self._open_producer().publish(
                message.body,
                exchange=queue.exchange,
                routing_key=ORDERS_QUEUE,
                declare=[queue],
                headers=message.headers,
                serializer="json",
                delivery_mode=PERSISTENT_DELIVERY_MODE,
                mandatory=True,  # an unroutable message comes back as an error instead of vanishing
                retry=False,
                timeout=self._timeout,
                confirm_timeout=self._timeout,
                **message.properties,
            )
        except Exception as error:
            self._discard_connection()
            raise PublishError(
                f"RabbitMQ did not confirm the task for order {order_id} ({type(error).__name__})."
            ) from error

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.release()
            except Exception:
                self._discard_connection()
        self._connection = self._producer = None

    def _open_producer(self) -> Producer:
        if self._producer is None:
            connection = Connection(
                self._broker_url,
                connect_timeout=self._timeout,
                transport_options={
                    "confirm_publish": True,
                    "read_timeout": self._timeout,
                    "write_timeout": self._timeout,
                },
            )
            self._connection = connection
            connection.ensure_connection(max_retries=0)  # one attempt; the caller decides when to retry
            self._producer = Producer(connection.channel())
        return self._producer

    def _discard_connection(self) -> None:
        """Drop the connection without the AMQP close handshake, which a broken broker may never answer."""
        if self._connection is not None:
            self._connection.collect()
        self._connection = self._producer = None


def publish_batch(session_factory: Callable[[], Session], publisher: OrderPublisher, limit: int = BATCH_LIMIT) -> int:
    """Claim up to `limit` unpublished events, oldest first, and publish them; return how many were published.

    On a broker failure the remaining claims are released for any publisher to retry,
    and the error propagates.
    """
    claimed = _claim(session_factory, limit)
    published = 0
    try:
        for event_id, order_id in claimed:
            publisher.publish_order(order_id, event_id, datetime.now(UTC))
            _mark_published(session_factory, event_id)
            published += 1
    except Exception:
        _release(session_factory, [event_id for event_id, _ in claimed[published:]])
        raise
    return published


class OutboxPublisher:
    """Runs `publish_batch` in a background thread from API startup to shutdown.

    It publishes again at once while batches come back full, waits
    `publisher_interval_ms` when idle, and backs off exponentially (up to 30 s)
    while publishing fails. `stop()` interrupts the wait.
    """

    def __init__(self, session_factory: Callable[[], Session], settings: Settings) -> None:
        self._session_factory = session_factory
        self._publisher = OrderPublisher(
            settings.require_broker_url("the outbox publisher"), settings.broker_timeout_seconds
        )
        self._interval = settings.publisher_interval_ms / 1000
        # Worst case for the publish in progress: connect, confirm, and close, each bounded.
        self._stop_timeout = 3 * settings.broker_timeout_seconds + 1
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="outbox-publisher", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread.ident is not None:
            self._thread.join(self._stop_timeout)
            if self._thread.is_alive():
                logger.warning("Outbox publisher did not stop within %s s; abandoning it.", self._stop_timeout)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        failures = 0
        try:
            while not self._stopping.is_set():
                try:
                    published = publish_batch(self._session_factory, self._publisher)
                except Exception as error:
                    failures += 1
                    wait = min(MAX_BACKOFF_SECONDS, self._interval * 2 ** (failures - 1))
                    logger.warning("Outbox publishing failed (%s); retrying in %.1f s.", _describe(error), wait)
                else:
                    failures = 0
                    wait = 0.0 if published == BATCH_LIMIT else self._interval
                self._stopping.wait(wait)
        finally:
            self._publisher.close()


def _claim(session_factory: Callable[[], Session], limit: int) -> list[tuple[UUID, UUID]]:
    """Lease up to `limit` unpublished, unclaimed (or lease-expired) events; return (event id, order id) oldest first."""
    claimable = (
        select(OutboxEvent.id)
        .where(
            OutboxEvent.published_at.is_(None),
            or_(OutboxEvent.claimed_until.is_(None), OutboxEvent.claimed_until < func.now()),
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)  # rows another publisher is claiming right now
    )
    with session_factory() as session, session.begin():
        rows = session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(claimable.scalar_subquery()))
            .values(claimed_until=func.now() + CLAIM_LEASE)
            .returning(OutboxEvent.id, OutboxEvent.order_id, OutboxEvent.created_at)
        ).all()
    return [(event_id, order_id) for event_id, order_id, _ in sorted(rows, key=lambda row: (row[2], row[0]))]


def _mark_published(session_factory: Callable[[], Session], event_id: UUID) -> None:
    with session_factory() as session, session.begin():
        session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
            .values(published_at=func.now(), claimed_until=None)
        )


def _release(session_factory: Callable[[], Session], event_ids: Sequence[UUID]) -> None:
    """Give unpublished claims back; if PostgreSQL is unreachable too, their leases simply run out."""
    if not event_ids:
        return
    try:
        with session_factory() as session, session.begin():
            session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id.in_(event_ids), OutboxEvent.published_at.is_(None))
                .values(claimed_until=None)
            )
    except Exception as error:
        logger.warning(
            "Could not release %d outbox claims (%s); their leases will expire.", len(event_ids), _describe(error)
        )


def _describe(error: Exception) -> str:
    """The error's type, plus its message when that is our own (database messages can quote SQL parameters)."""
    return str(error) if isinstance(error, PublishError) else type(error).__name__
