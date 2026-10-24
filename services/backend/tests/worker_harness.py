"""Run the CloudCart fulfillment worker with TEST-ONLY faults; integration tests start it as a subprocess.

The application never imports this file. Faults are chosen by environment variables:

- CLOUDCART_TEST_FAILING_ATTEMPTS=N: the simulated dispatch raises on attempts 1..N of every order.
- CLOUDCART_TEST_CRASH_AFTER_TASK=1: the process kills itself with SIGKILL as soon as its first
  task returns, after the task's database commit and before the broker acknowledgement.
"""

import os
import signal
from uuid import UUID

from celery.signals import task_postrun

from cloudcart.jobs import tasks, worker

FAILING_ATTEMPTS = int(os.environ.get("CLOUDCART_TEST_FAILING_ATTEMPTS", "0"))
CRASH_AFTER_TASK = os.environ.get("CLOUDCART_TEST_CRASH_AFTER_TASK") == "1"


class SimulatedDispatchError(RuntimeError):
    """The simulated dispatch failed on purpose."""


if FAILING_ATTEMPTS:
    working_dispatch = tasks.simulate_dispatch

    def failing_dispatch(order_id: UUID, attempt: int, delay_ms: int) -> None:
        if attempt <= FAILING_ATTEMPTS:
            raise SimulatedDispatchError(f"simulated dispatch failure on attempt {attempt}")
        working_dispatch(order_id, attempt, delay_ms)

    tasks.simulate_dispatch = failing_dispatch

if CRASH_AFTER_TASK:

    @task_postrun.connect(weak=False)
    def crash_before_acknowledgement(**_: object) -> None:
        os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    worker.main()
