# Current handoff

Updated: 2026-10-24 (Asia/Thimphu).

## Read first

1. [Project status](../../PROJECT_STATUS.md)
2. [Approved design](../superpowers/specs/2026-10-16-cloudcart-design.md)
3. [Implementation plan](../superpowers/plans/2026-10-16-cloudcart-implementation.md)
4. [Working conventions](../../CONTRIBUTING.md)
5. [Decisions](DECISIONS.md), especially D019–D023 for the P02 access contract and D024–D026 for checkout and orders
6. [Host prerequisites](../instructor/prerequisites.md) and [version matrix](../../deploy/platform/versions.yaml)

## Current state

P01, P02, and P03 are done and verified ([P01 evidence](VERIFICATION.md#2026-10-24--p01-runnable-database-foundation), [P02 evidence](VERIFICATION.md#2026-10-24--p02-catalog-persistent-carts-and-access-boundaries), [P03 evidence](VERIFICATION.md#2026-10-24--p03-atomic-checkout-and-durable-order-contract)). P04–P12 are not started; begin each only when the instructor requests it.

Git: `main` holds P01, P02, and P03. P03 (`50aca8d` tests, `e910f54` implementation, `bf08d29` review fix, `a03a3ae` and `de1391e` records) was merged from [PR #2](https://github.com/sarojsanyasicst/DSO202-K8s/pull/2) by local merge commit `fb50bc9` on 2026-10-24, which keeps the noreply identity; branch `claude/p03-start-ce835d` still exists locally and on `origin`. P02 (`c01e916`, `6f9f7c0`, `ae2ec1e`) was merged through [PR #1](https://github.com/sarojsanyasicst/DSO202-K8s/pull/1) as merge commit `97aba5a` on 2026-10-24; branch `claude/p02-catalog-carts-access-875a84` still exists locally and on `origin`. Merges made on github.com use the GitHub account's email settings, not the local noreply configuration: `97aba5a` carries the account's primary email, which the instructor chose to keep. Enable GitHub's "Keep my email addresses private" setting, or merge locally, to keep later merge commits on the noreply identity. Remote `origin` is the public GitHub repository https://github.com/sarojsanyasicst/DSO202-K8s, so never commit credentials, personal data, or machine secrets. Commits use the instructor's GitHub noreply identity.

What exists for later tasks to build on:

- `services/backend/` is a uv project pinned to Python `>=3.13,<3.14` with 36 locked packages. Run commands through the Make targets or `uv run --locked --project services/backend ...`.
- Settings: `Settings.from_env()` reads `CLOUDCART_*`; P02 added `CLOUDCART_COOKIE_SECURE` (default true). `Database(settings)` exposes `session_factory`, `session_scope()`, `dispose()`; `db.py` also holds the per-request FastAPI dependency `DbSession` (commits or rolls back before the response).
- Schema (Alembic head `e7b83d9b2137`, previous `371b57c4f5aa`): `products` (unique slug `sku`, `price_cents` > 0, `currency` = USD, `stock` >= 0), `guests` and `instructor_sessions` (token SHA-256 hashes, `expires_at`), `instructors`, `carts` (unique `guest_id`, `version`), `cart_items` (primary key cart + product, quantity > 0), `orders` (status check, `BIGINT` total, unique `guest_id` + `idempotency_key`, `request_fingerprint`), `order_items` (name and unit price at checkout), `outbox_events` (unique `order_id`, nullable `published_at`), `receipts` (unique `order_id`, `issued_at`). Order tables have no `ON DELETE CASCADE`.
- API under `/api/v1`: `GET /products`; `GET /session` (only route that creates a guest; returns `{csrf_token, expires_at}`); `GET /cart`; `PUT`/`DELETE /cart/items/{product_id}`; `POST /orders` (checkout, `Idempotency-Key`); `GET /orders`, `/orders/{order_id}`, `/orders/{order_id}/receipt`; `POST /admin/login`; `PUT /admin/products/{product_id}/stock`. Statuses and limits are in D020–D026 and the OpenAPI schema.
- Interfaces: `identity.security.ensure_guest(session, token) -> GuestSession`; `cart.service.set_cart_item(session, guest_id, product_id, quantity) -> CartView`; `cart.service.lock_guest_cart(session, guest_id) -> Cart` and `clear_cart(session, cart) -> CartView`; `orders.service.checkout(session, guest_id, cart_version, payment_outcome, idempotency_key) -> CheckoutResult(order, replayed)`, `get_order`, `list_orders`, `get_receipt`; ORM models `Order` (relationships `items`, `outbox_event`, `receipt`, loaded with `selectin`), `OrderItem`, `OutboxEvent`, `Receipt`; `seed.seed_database(session, admin_password)`; `python -m cloudcart.seed` with `CLOUDCART_SEED_ADMIN_PASSWORD`.
- Test fixtures: `test_database_url`, `integration_settings`, `database`, `open_client` (TestClient on `https://testserver`), autouse per-test truncation. Shared helpers in `tests/helpers.py`: `OpenClient`, `run_sql` (returns rows), `Browser`, `start_guest`. Concurrency tests use `wait_until_blocked(database, pid, by=...)` (polls `pg_blocking_pids`). `make test-deps-up` / `make test-deps-down` manage the `cloudcart-test` Compose project (PostgreSQL 127.0.0.1:15432, AMQP 15672, management 15673).

## Next useful action

When the instructor requests it, begin P04 / Task 4: write the failing delivery and fulfillment tests (`test_delivery.py`, `test_fulfillment.py`), then the outbox publisher, Celery app/tasks, and the worker.

## Carried-forward notes

- **Task 4:**
  - `cloudcart.db` imports FastAPI (for `DbSession`); the worker shares the package and image, so this is accepted. Move it to an API-only module if worker import weight matters.
  - Returning reserved stock on terminal failure must follow D025's lock order: products in id order (and any cart before products). Re-check `orders.status` under a row lock so stock is returned exactly once.
  - Outbox: add the claim columns and a partial index on unpublished events with the publisher's claim query; set `published_at` only after a confirmed, routable publish. `OrderView.publication_pending` is `published_at IS NULL`.
  - Receipts: insert with `ON CONFLICT (order_id) DO NOTHING` (or rely on `uq_receipts_order_id`) so duplicate deliveries create one receipt. Status values are fixed by the `ck_orders_status_known` constraint.
  - Add an automated model/migration drift check (`alembic check` or `compare_metadata`) to the integration suite before changing order tables (P03 review minor).
- **P03 review minors (deferred):**
  - FastAPI parses JSON before running dependencies, so malformed JSON gets 422 even cross-origin or without a session (no state change). No test shows that a missing CSRF token (403) wins over a missing `Idempotency-Key` or bad body (422).
  - No HTTP-level test of a write followed by failure: a fresh guest posting `cart_version: 0` makes `lock_guest_cart` insert a cart row before the 409; assert it is rolled back.
  - `clear_cart` builds a `CartView` that checkout discards (two extra queries per checkout).
  - A guest with no cart row and `cart_version` ≠ 0 gets "The cart changed…" (correct 409, imprecise wording).
- **Task 5 (checkout UI):** send a fresh random `Idempotency-Key` per checkout attempt and resend it unchanged on network retries; on 409 reload the cart (stale, empty, or stock) or use a new key (key reused); on 402 show the declined payment and keep the cart. 201 carries `Location: /api/v1/orders/{id}`.
- **Task 5 (storefront):**
  - Bootstrap with one `GET /api/v1/session` at a time; two simultaneous first calls create two guests and a cookie/CSRF mismatch. After a 401, or a CSRF 403, call `/session` again.
  - Send `X-CSRF-Token` on every PUT/POST/DELETE. Any dev or preview proxy must keep the original `Host` (for example Vite `changeOrigin: false`), or run Playwright through the gateway; otherwise every change gets 403.
  - Add the same-origin guard to `GET /session` (403 on `Sec-Fetch-Site: cross-site`, no Set-Cookie) together with a browser test: today a cross-site top-level navigation can replace a guest's cookie and orphan their cart (nothing leaks).
  - Create the eight product images at `services/frontend/public/products/<sku>.svg` matching the seed SKUs in `seed.py`.
- **Task 6:**
  - Add Uvicorn together with the API launch command (it was deliberately removed from P01). Refresh its versions.yaml entry; `verified_by` still cites an earlier uv.lock resolution.
  - Add the production-mode setting that rejects the lab endpoint.
  - libpq `tcp_user_timeout` only takes effect on Linux, which is fine for the containers.
  - Recheck `pycparser 3.12` (published two days before it was locked) at the release pin review.
  - Consider `hide_parameters=True` on the engine so SQL errors in Job/API logs do not include Argon2 or token hashes.
- **Task 6/8 (login cost):** Argon2 defaults use 64 MiB per hash, and login holds a pooled DB connection during verification. Before Task 8 sizes API memory limits, set explicit `PasswordHasher` parameters and bound concurrent logins (for example a `BoundedSemaphore` that answers 503 when busy). `verify_password` does not catch `InvalidHashError` (a corrupted stored hash gives 500, accepted for now).
- **Task 7:**
  - The gateway must pass the original `Host` header to the API (Traefik's default); verify it in smoke acceptance, since the same-origin guard returns 403 otherwise.
  - Serve over HTTPS or set `CLOUDCART_COOKIE_SECURE=false` deliberately; browsers drop Secure cookies on plain HTTP except localhost.
  - Supply `CLOUDCART_SEED_ADMIN_PASSWORD` to the seed Job from a Secret. Rotating it and rerunning the seed changes the password for new logins; existing instructor sessions live up to 8 hours. Document this in the operator notes.
  - Normalize the versions.yaml schema (exact vs range fields; kubectl is `v1.36.x`; helm is pinned at v4.3.1 while v4.3.0 is installed) before preflight reads it.
  - Close the `partially_verified` edges: Gateway API minimum Kubernetes version, and kube-prometheus-stack on 1.36.
  - Consider an advisory lock for migration Jobs.
  - Size the DB pool against PostgreSQL `max_connections` across replicas.
- **Task 9:** `scripts/traffic.py` must reuse one cookie jar per virtual user and log in once; every cookieless `GET /session` inserts a `guests` row and nothing cleans them up yet (cleanup needs an owner and an `expires_at` index, and must skip guests with orders: the `orders` foreign key has no cascade). Probes must never call `/session`. Checkout lock waits beyond `statement_timeout` (5 s) or a deadlock surface as an unhandled 500; consider mapping lock timeouts to 503 with `Retry-After` (a retry with the same key is safe).
- **Instructor decisions pending:**
  - Ratify the D014 version matrix in [DECISIONS.md](DECISIONS.md).
  - Docker Desktop VM memory: ~7.75 GiB observed, against the 12–14 GiB planning estimate. Increase it before P07, or measure and accept it.
  - Optional: upgrade uv so local tests can run CPython 3.13.17, the same patch as the image (they currently use 3.13.15).
- **Host hygiene:** uv's interpreter store holds CPython 3.15.0rc2 (unused) and 3.13.15. A `~/.local/bin/python3.13` link was added in P01. Remove them only if the instructor wants.
- `promtool` is missing; it is needed for P11 rule tests.

## Known constraints and open inputs

- Apple M4, 24 GB RAM; kind target is 1 control plane + 2 workers. An unrelated kind cluster `dso202` exists and owns 127.0.0.1:80/443. Never modify or delete it. The current context is `kind-dso202`, so always name `kind-cloudcart` explicitly.
- Students receive prebuilt images; CI/image-building instruction stays outside classroom scope.
- Argo CD needs a reachable Git source in P10. The public `origin` repository is a candidate; the instructor confirms the URL, revision, and values path then.
- Baseline exclusions are unchanged: no real payment/shipping, object storage, Redis, extra business microservices, centralized logs/tracing, or stateful HA.

## Verification and continuation hygiene

Record runtime checks in [VERIFICATION.md](VERIFICATION.md), update the milestone board, append the session log, and replace this handoff with the actual next continuation point.
