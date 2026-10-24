"""Idempotent order fulfillment, run by the worker for every delivery of `cloudcart.orders.fulfill`.

RabbitMQ may deliver a task more than once: after a publisher crash, a worker
crash, or a lost connection. Every step therefore locks the order row and checks
its status first. A finished order (fulfilled or failed) is never changed again,
the unique receipt per order backs that up, and reserved stock is returned at
most once.

Each delivery of an unfinished order starts an attempt: it counts the attempt in
`orders.fulfillment_attempts` and shows the order as processing (committed, so
the shopper sees it), simulates packing and dispatch, and then issues the
receipt and marks the order fulfilled in one transaction. The message is
acknowledged only after that, or after a final failure, is committed.

A failed attempt waits an exponential backoff (1×, 2×, 4× the configured base)
and rejects the message with requeue, so RabbitMQ delivers it again. When the
fourth attempt (the first plus three retries) fails, or a delivery finds four
attempts already used (for example after repeated worker crashes), the order
fails: its stock is returned and the reason recorded in one transaction.
PostgreSQL errors before an attempt is recorded do not use up attempts: without
its database the worker can neither process nor record a failure, so it waits
the longest backoff and requeues the delivery until PostgreSQL answers.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from celery import Celery
from celery.exceptions import Reject
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from cloudcart.catalog.models import Product
from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.jobs.celery_app import FULFILL_TASK
from cloudcart.orders.models import FAILURE_REASON_MAX_LENGTH, Order, OrderStatus, Receipt
from cloudcart.orders.schemas import FulfillmentResult

logger = logging.getLogger(__name__)

MAX_FULFILLMENT_ATTEMPTS = 4  # the first attempt plus at most three retries
FINISHED_STATUSES = frozenset({"fulfilled", "failed"})
# Errors that mean PostgreSQL could not be reached or answer in time.
DATABASE_UNAVAILABLE = (OperationalError, InterfaceError)


@dataclass(frozen=True)
class Attempt:
    order_status: OrderStatus
    number: int | None  # the attempt just started; None when the order is finished or out of attempts


class UnknownOrderError(LookupError):
    """A task names an order that does not exist."""


def begin_attempt(session: Session, order_id: UUID) -> Attempt:
    """Count a new attempt and mark the order processing, unless it is finished or out of attempts."""
    order = _lock_order(session, order_id)
    if order.status in FINISHED_STATUSES or order.fulfillment_attempts >= MAX_FULFILLMENT_ATTEMPTS:
        return Attempt(order.status, None)
    order.fulfillment_attempts += 1
    order.status = "processing"
    session.flush()
    return Attempt("processing", order.fulfillment_attempts)


def fulfill_order(session: Session, order_id: UUID) -> FulfillmentResult:
    """Issue the order's receipt and mark it fulfilled; a finished order is reported unchanged."""
    order = _lock_order(session, order_id)
    if order.status in FINISHED_STATUSES:
        return _result(session, order, already_applied=True)
    session.execute(
        insert(Receipt).values(id=uuid4(), order_id=order.id).on_conflict_do_nothing(index_elements=["order_id"])
    )
    order.status = "fulfilled"
    session.flush()
    return _result(session, order, already_applied=False)


def fail_order(session: Session, order_id: UUID, reason: str) -> FulfillmentResult:
    """Return the order's reserved stock and mark it failed with `reason`; a finished order is reported unchanged.

    Product rows are updated in product-id order, the lock order every stock writer follows.
    """
    order = _lock_order(session, order_id)
    if order.status in FINISHED_STATUSES:
        return _result(session, order, already_applied=True)
    for item in sorted(order.items, key=lambda item: item.product_id):
        session.execute(
            update(Product).where(Product.id == item.product_id).values(stock=Product.stock + item.quantity)
        )
    order.status = "failed"
    order.failure_reason = reason[:FAILURE_REASON_MAX_LENGTH]
    session.flush()
    return _result(session, order, already_applied=False)


def simulate_dispatch(order_id: UUID, attempt: int, delay_ms: int) -> None:
    """Stand-in for packing and dispatch: takes `delay_ms`, so queues and processing time are observable."""
    time.sleep(delay_ms / 1000)


def register_fulfillment(app: Celery, database: Database, settings: Settings) -> None:
    """Register the `cloudcart.orders.fulfill` task on the worker's Celery application."""

    @app.task(name=FULFILL_TASK, acks_late=True, reject_on_worker_lost=True, ignore_result=True)
    def fulfill(order_id: str, enqueued_at: str) -> None:
        handle_delivery(database, settings, UUID(order_id), datetime.fromisoformat(enqueued_at))


def handle_delivery(database: Database, settings: Settings, order_id: UUID, enqueued_at: datetime) -> None:
    """Process one delivery. Returning acknowledges it; `Reject(requeue=True)` has RabbitMQ deliver it again."""
    backoff = settings.fulfillment_retry_backoff_ms / 1000
    try:
        _deliver(database, settings, order_id, enqueued_at, backoff)
    except UnknownOrderError:
        logger.error("Order %s does not exist; dropping its fulfillment task.", order_id)
    except DATABASE_UNAVAILABLE as error:
        _retry_later(
            order_id, backoff * 2 ** (MAX_FULFILLMENT_ATTEMPTS - 2), f"PostgreSQL unavailable ({type(error).__name__})"
        )


def _deliver(database: Database, settings: Settings, order_id: UUID, enqueued_at: datetime, backoff: float) -> None:
    with database.session_scope() as session:
        attempt = begin_attempt(session, order_id)
    if attempt.number is None:
        if attempt.order_status not in FINISHED_STATUSES:  # earlier deliveries used up the attempts
            _record_failure(database, order_id, f"Gave up after {MAX_FULFILLMENT_ATTEMPTS} fulfillment attempts.")
        return

    queued_seconds = (datetime.now(UTC) - enqueued_at).total_seconds()
    logger.info("Order %s: attempt %d started %.1f s after publication.", order_id, attempt.number, queued_seconds)
    try:
        simulate_dispatch(order_id, attempt.number, settings.fulfillment_delay_ms)
        with database.session_scope() as session:
            fulfill_order(session, order_id)
    except Exception as error:
        if attempt.number >= MAX_FULFILLMENT_ATTEMPTS:
            _record_failure(
                database,
                order_id,
                f"Fulfillment failed {MAX_FULFILLMENT_ATTEMPTS} times; last error: {type(error).__name__}.",
            )
            return
        _retry_later(
            order_id, backoff * 2 ** (attempt.number - 1), f"attempt {attempt.number} failed ({type(error).__name__})"
        )
    logger.info("Order %s fulfilled on attempt %d.", order_id, attempt.number)


def _record_failure(database: Database, order_id: UUID, reason: str) -> None:
    with database.session_scope() as session:
        fail_order(session, order_id, reason)
    logger.warning("Order %s failed: %s Its reserved stock was returned.", order_id, reason)


def _retry_later(order_id: UUID, delay_seconds: float, reason: str) -> None:
    logger.warning("Order %s: %s; delivering again in %.2f s.", order_id, reason, delay_seconds)
    time.sleep(delay_seconds)
    raise Reject(reason, requeue=True)


def _lock_order(session: Session, order_id: UUID) -> Order:
    order = session.scalars(
        select(Order).where(Order.id == order_id).with_for_update().execution_options(populate_existing=True)
    ).one_or_none()
    if order is None:
        raise UnknownOrderError(order_id)
    return order


def _result(session: Session, order: Order, already_applied: bool) -> FulfillmentResult:
    receipt_id = session.scalar(select(Receipt.id).where(Receipt.order_id == order.id))
    return FulfillmentResult(
        order_id=order.id, status=order.status, receipt_id=receipt_id, already_applied=already_applied
    )
