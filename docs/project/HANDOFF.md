# Current handoff

Updated: 2026-10-24 (Asia/Thimphu).

## Read first

1. [Project status](../../PROJECT_STATUS.md)
2. [Approved design](../superpowers/specs/2026-10-16-cloudcart-design.md)
3. [Implementation plan](../superpowers/plans/2026-10-16-cloudcart-implementation.md)
4. [Working conventions](../../CONTRIBUTING.md)
5. [Decisions](DECISIONS.md), especially D019–D023 for the P02 access contract
6. [Host prerequisites](../instructor/prerequisites.md) and [version matrix](../../deploy/platform/versions.yaml)

## Current state

P01 and P02 are done and verified ([P01 evidence](VERIFICATION.md#2026-10-24--p01-runnable-database-foundation), [P02 evidence](VERIFICATION.md#2026-10-24--p02-catalog-persistent-carts-and-access-boundaries)). P03–P12 are not started; begin each only when the instructor requests it.

Git: `main` holds P01. P02 is on branch `claude/p02-catalog-carts-access-875a84` (code `c01e916`, `6f9f7c0`, plus the project-record commit) and is **not merged**; merging and pushing are the instructor's decision. Remote `origin` is the public GitHub repository https://github.com/sarojsanyasicst/DSO202-K8s, so never commit credentials, personal data, or machine secrets. Commits use the instructor's GitHub noreply identity.

What exists for later tasks to build on:

- `services/backend/` is a uv project pinned to Python `>=3.13,<3.14` with 36 locked packages. Run commands through the Make targets or `uv run --locked --project services/backend ...`.
- Settings: `Settings.from_env()` reads `CLOUDCART_*`; P02 added `CLOUDCART_COOKIE_SECURE` (default true). `Database(settings)` exposes `session_factory`, `session_scope()`, `dispose()`; `db.py` also holds the per-request FastAPI dependency `DbSession` (commits or rolls back before the response).
- Schema (Alembic head `371b57c4f5aa`): `products` (unique slug `sku`, `price_cents` > 0, `currency` = USD, `stock` >= 0), `guests` and `instructor_sessions` (token SHA-256 hashes, `expires_at`), `instructors`, `carts` (unique `guest_id`, `version`), `cart_items` (primary key cart + product, quantity > 0).
- API under `/api/v1`: `GET /products`; `GET /session` (only route that creates a guest; returns `{csrf_token, expires_at}`); `GET /cart`; `PUT`/`DELETE /cart/items/{product_id}`; `POST /admin/login`; `PUT /admin/products/{product_id}/stock`. Statuses and limits are in D020–D023 and the OpenAPI schema.
- Interfaces: `identity.security.ensure_guest(session, token) -> GuestSession`; `cart.service.set_cart_item(session, guest_id, product_id, quantity) -> CartView`; `seed.seed_database(session, admin_password)`; `python -m cloudcart.seed` with `CLOUDCART_SEED_ADMIN_PASSWORD`.
- Test fixtures: `test_database_url`, `integration_settings`, `database`, `open_client` (TestClient on `https://testserver`), autouse per-test truncation. `make test-deps-up` / `make test-deps-down` manage the `cloudcart-test` Compose project (PostgreSQL 127.0.0.1:15432, AMQP 15672, management 15673).

## Next useful action

When the instructor requests it, begin P03 / Task 3: write the failing checkout and concurrency tests (`test_checkout.py`, `test_checkout_concurrency.py`, extensions to `test_access.py`), then orders models/routes/service, the next Alembic revision, and the outbox insert.

## Carried-forward notes

- **Task 3 (checkout):**
  - Lock order: adding a cart line locks the cart row `FOR UPDATE`, then takes the foreign key's `KEY SHARE` on the product row. Lock the cart before products, or use guarded `UPDATE products SET stock = stock - n WHERE stock >= n` (a `NO KEY UPDATE` does not conflict with `KEY SHARE`). The cart-locking helper `_guest_cart` in `cart/service.py` is private; add a public helper or a dedicated lock query.
  - Empty-cart checkout rejection belongs to Task 3 (P02 only returns an empty cart at version 0). Setting a line to its current quantity still raises the version.
  - Consolidate the duplicated test helpers (`OpenClient` alias in `tests/integration/conftest.py` and `test_access.py`; two `run_sql` helpers with different return semantics) when extending `test_access.py`.
  - Add a database-free unit test for `RequestBodyLimit` with several `more_body=True` messages the next time `main.py` changes.
- **Task 4:** `cloudcart.db` now imports FastAPI (for `DbSession`); the worker shares the package and image, so this is accepted. Move it to an API-only module if worker import weight matters.
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
- **Task 9:** `scripts/traffic.py` must reuse one cookie jar per virtual user and log in once; every cookieless `GET /session` inserts a `guests` row and nothing cleans them up yet (cleanup needs an owner and an `expires_at` index). Probes must never call `/session`.
- **Instructor decisions pending:**
  - Merge `claude/p02-catalog-carts-access-875a84` into `main` and push.
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
