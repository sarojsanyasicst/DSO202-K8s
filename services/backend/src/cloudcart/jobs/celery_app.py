"""The Celery transport contract shared by the API's outbox publisher and the fulfillment worker.

One durable classic queue, `orders`, behind a direct exchange of the same name,
carries JSON-only task messages for `cloudcart.orders.fulfill`. Both sides
declare the queue with identical arguments, so either may start first.
"""

from celery import Celery
from kombu import Exchange, Queue

from cloudcart.config import Settings

ORDERS_QUEUE = "orders"
FULFILL_TASK = "cloudcart.orders.fulfill"


def orders_queue() -> Queue:
    """The durable orders queue. Messages for it are published persistent (delivery mode 2)."""
    return Queue(
        ORDERS_QUEUE,
        Exchange(ORDERS_QUEUE, type="direct", durable=True),
        routing_key=ORDERS_QUEUE,
        durable=True,
    )


def create_celery(settings: Settings, component: str) -> Celery:
    """A Celery application for `component`, configured for at-least-once, duplicate-tolerant delivery.

    - Late acknowledgement and prefetch 1: a task is acknowledged only after it returns,
      and a worker holds at most one unacknowledged task, so a crash or a lost connection
      sends the task back to the queue for another delivery.
    - A task whose worker is lost is requeued. The solo pool cannot cancel a task that is
      running when the broker connection drops: it finishes, its acknowledgement fails, and
      RabbitMQ redelivers it to a worker that tolerates duplicates.
    - A task that raises is acknowledged and dropped. Fulfillment raises only for a malformed
      message or a bug; database errors requeue instead (see cloudcart.jobs.tasks).
    - Results are not stored: PostgreSQL holds every business outcome.
    """
    app = Celery("cloudcart", set_as_current=False)
    app.conf.update(
        broker_url=settings.require_broker_url(component),
        broker_connection_timeout=settings.broker_timeout_seconds,
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=None,  # keep reconnecting through a broker outage
        broker_transport_options={"confirm_publish": True},
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        result_backend=None,
        task_queues=[orders_queue()],
        task_default_queue=ORDERS_QUEUE,
        task_create_missing_queues=False,
        task_default_delivery_mode="persistent",
        task_acks_late=True,
        task_acks_on_failure_or_timeout=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_cancel_long_running_tasks_on_connection_loss=True,
        # Remote control needs a transient non-exclusive reply queue, which RabbitMQ 4 refuses
        # by default; worker probes must not depend on `celery inspect` anyway.
        worker_enable_remote_control=False,
        worker_send_task_events=False,
        enable_utc=True,
        timezone="UTC",
    )
    return app
