"""Fulfillment worker entry point: `python -m cloudcart.jobs.worker`.

Runs one Celery worker process with the solo pool on the `orders` queue: one task
at a time, at most one unacknowledged message, and a single process per
container, so each worker Pod is one observable scaling unit. SIGTERM starts a
warm shutdown: the worker stops taking tasks, finishes the one in progress, and
exits. A task takes at most the simulated dispatch delay plus the longest retry
backoff and its bounded database calls, so a termination grace period of about
30 s covers it.
"""

import os

from celery import bootsteps
from celery.worker import WorkController

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.jobs.celery_app import ORDERS_QUEUE, create_celery
from cloudcart.jobs.tasks import register_fulfillment

WAKE_INTERVAL_SECONDS = 1.0


class PromptShutdown(bootsteps.StartStopStep):
    """Wake the worker's event loop every second.

    An idle loop otherwise sleeps up to 10 s between timers, and only notices a
    SIGTERM when it wakes, which delays every rollout and scale-down.
    """

    requires = {"celery.worker.components:Timer"}

    def start(self, worker: WorkController) -> None:
        worker.timer.call_repeatedly(WAKE_INTERVAL_SECONDS, _wake)


def _wake() -> None:
    pass


def main() -> None:
    settings = Settings.from_env()
    app = create_celery(settings, "the fulfillment worker")
    app.steps["worker"].add(PromptShutdown)
    database = Database(settings)
    register_fulfillment(app, database, settings)
    try:
        app.worker_main(
            [
                "worker",
                "--pool=solo",
                "--concurrency=1",
                f"--queues={ORDERS_QUEUE}",
                # Workers share nothing but the queue: skip worker-to-worker chatter.
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "--loglevel=INFO",
                f"--hostname=cloudcart-worker-{os.getpid()}@%h",
            ]
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
