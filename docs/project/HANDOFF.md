# Current handoff

Updated: 2026-10-16 (Asia/Thimphu).

## Read first

1. [Project status](../../PROJECT_STATUS.md)
2. [Approved design](../superpowers/specs/2026-10-16-cloudcart-design.md)
3. [Implementation plan](../superpowers/plans/2026-10-16-cloudcart-implementation.md)
4. [Working conventions](../../CONTRIBUTING.md)

## Current state

Project setup S00 is complete. The instructor approved the architecture and then requested folder structure and progress files. Application tasks P01–P12 have not started. The workspace has no initialized Git repository and no runnable project dependency configuration yet.

The application is CloudCart: a modular FastAPI backend and Celery worker sharing Python code, React frontend, PostgreSQL, and RabbitMQ. Checkout must reserve stock atomically, write an outbox event, and tolerate duplicate task delivery. The course covers Kubernetes deployment through metrics monitoring.

Existing design and plan files have been preserved. Empty source/deployment folders contain `.gitkeep` markers. Their existence does not mean code or infrastructure has been implemented. Backend/frontend and infrastructure README files explain ownership and intended contents.

## Next useful action

When the instructor requests application implementation, begin P01 / Task 1 of the detailed plan: inspect prerequisites and current contexts, establish locked backend configuration, disposable test dependencies, database lifecycle, and migration foundation. Follow the active execution workflow and the latest user instructions; do not infer authorization to execute all 12 tasks from the structure-only request.

Do not jump directly into Kubernetes resources. The first working application slice should lead toward PostgreSQL + product API + minimal product page, while preserving the detailed plan's access and transaction requirements.

## Known constraints and open inputs

- Apple M4, 24 GB RAM; kind target is 1 control plane + 2 workers.
- Actual Docker allocation, tool availability, compatible version pins, and runtime capacity have not been checked.
- Students receive prebuilt images; CI/image-building instruction stays outside the classroom scope.
- Argo CD needs a reachable Git source later; no URL has been supplied.
- No real payment/shipping, object storage, Redis, extra business microservices, centralized logs/tracing, or stateful HA in the baseline.
- Session durations and conditional AMD64 image distribution remain implementation/rehearsal choices.

## Verification and continuation hygiene

Only documentation/folder checks apply to the completed setup. See [verification evidence](VERIFICATION.md). Record future runtime checks there, update the milestone board, append the session log, and replace this handoff with the actual next continuation point.
