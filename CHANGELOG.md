# Changelog

## Unreleased

### Added

- P05 storefront and instructor view (`services/frontend`, React 19 with TypeScript and Vite 8): product grid with bundled product images, persistent cart, prominent simulated payment, checkout that reuses its `Idempotency-Key` on retries after a dropped connection or a 5xx, order history, order pages that poll every two seconds and show waiting to be queued, queued, being packed, fulfilled, or failed, printable receipts, and an instructor view with order counters, recent orders across guests, stock changes, and sign-out. The footer shows the storefront and API versions. API types are generated from the committed OpenAPI document (`make frontend-types`).
- API routes `GET /api/v1/admin/session`, `POST /api/v1/admin/logout`, `GET /api/v1/admin/orders`, and `GET /api/v1/version` (setting `CLOUDCART_RELEASE_VERSION`); `GET /api/v1/session` now refuses cross-site requests.
- Playwright browser tests (`make test-e2e`) against a production build, the real API with its publisher, a worker subprocess, and the disposable dependencies, including WCAG 2.1 AA (axe), 360 px layout, and keyboard checks; backend tests for the new routes and an OpenAPI contract test.

- P04 reliable publisher and fulfillment worker: an `OutboxPublisher` thread in each API process claims outbox events (`FOR UPDATE SKIP LOCKED` plus a 60 s lease) and publishes persistent, mandatory Celery task messages over a confirm-mode RabbitMQ connection, marking events published only after confirmation; broker calls are bounded and failures back off exponentially. Worker command `python -m cloudcart.jobs.worker` (Celery 5.6.3 solo pool, late acknowledgement, prefetch 1) shows orders as processing, issues one receipt, and marks them fulfilled; failed attempts are retried with backoff at most three times, after which the order fails and its stock is returned once. Database errors outside an attempt (PostgreSQL unreachable or refusing statements) requeue the delivery without using attempts. New settings `CLOUDCART_BROKER_URL`, `CLOUDCART_BROKER_TIMEOUT_SECONDS`, `CLOUDCART_PUBLISHER_ENABLED`, `CLOUDCART_PUBLISHER_INTERVAL_MS`, `CLOUDCART_FULFILLMENT_DELAY_MS`, and `CLOUDCART_FULFILLMENT_RETRY_BACKOFF_MS`.
- Alembic revision `674c483b8f18`: `orders.fulfillment_attempts` and `orders.failure_reason`, `outbox_events.claimed_until`, and a partial index on unpublished events.
- Integration tests for publication and fulfillment (`test_delivery.py`, `test_fulfillment.py`) with a loopback TCP fault proxy and a worker test harness, an `alembic check` drift test, and unit tests for the new settings and startup checks.
- P03 atomic checkout and durable order contract: `POST /api/v1/orders` checks out the guest's cart in one transaction (cart lock, then product locks in id order, guarded stock decrement, server-side prices, one outbox event, cart emptied) with a required `Idempotency-Key`; replays return the same order (200), conflicts return 409, a declined simulated payment 402. Guest-scoped `GET /api/v1/orders`, `/orders/{id}`, and `/orders/{id}/receipt`.
- Alembic revision `e7b83d9b2137`: `orders` (unique guest + key), `order_items`, `outbox_events` (one per order), and `receipts` (one per order).
- PostgreSQL integration tests for checkout and concurrency (`test_checkout.py`, `test_checkout_concurrency.py`), checkout and order-ownership cases in `test_access.py`, shared test helpers (`tests/helpers.py`), and a database-free `RequestBodyLimit` unit test.
- P02 catalog, persistent carts, and access boundaries: public product listing; guest sessions and persistent carts with quantity/line/stock limits and a version counter; instructor login (Argon2id via `argon2-cffi` 25.1.0) and instructor-only stock updates; session-bound CSRF tokens, Origin/`Sec-Fetch-Site` checks, HttpOnly `SameSite=Strict` cookies (`CLOUDCART_COOKIE_SECURE`), and a 16 KiB request-body limit.
- First Alembic revision (`371b57c4f5aa`) and the idempotent seed command `python -m cloudcart.seed` (`CLOUDCART_SEED_ADMIN_PASSWORD`).
- PostgreSQL integration tests for shopping and access rules (`test_shopping.py`, `test_access.py`).
- P01 backend foundation: locked Python 3.13 uv project, validated environment settings with bounded lab limits, database session lifecycle with bounded timeouts, FastAPI app factory, and Alembic scaffolding.
- Disposable PostgreSQL 18.6 and RabbitMQ 4.3.7 test dependencies (`tests/compose.yaml`) with `make test-unit`, `test-integration`, `test-deps-up`, and `test-deps-down`.
- Unit and PostgreSQL/RabbitMQ integration tests for settings, sessions, timeouts, migrations, and test-fixture safety.
- Version matrix (`deploy/platform/versions.yaml`) and instructor host prerequisites (`docs/instructor/prerequisites.md`).
- Approved CloudCart architecture and a 12-task implementation plan.
- Project folders for application code, containers, deployments, monitoring, scripts, tests, teaching material, and generated artifacts.
- A milestone status board, roadmap, decision log, session history, verification record, and next-session handoff.
- Working conventions and ignore rules for local/generated material.

No application release has been built or deployed.
