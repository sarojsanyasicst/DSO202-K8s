# Changelog

## Unreleased

### Added

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
