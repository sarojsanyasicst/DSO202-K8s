# Verification record

Evidence belongs here; milestone status belongs in [PROJECT_STATUS.md](../../PROJECT_STATUS.md). Append future records with date, milestone, checks, result, limitations, and artifact locations. Generated outputs go under ignored `artifacts/verification/`; keep sanitized summaries here.

## 2026-10-16 — S00 structure and tracking

**Scope:** project folders, Markdown progress records, links, and planning consistency.

**Checks:** inspect the directory inventory; verify all local Markdown document targets exist; verify P01–P12 match the 12 implementation tasks and start as Not started; verify each planned source/deployment folder exists; check placeholder/README coverage; confirm application code and runtime configuration have not been introduced.

**Result:** passed. A one-off Python standard-library audit checked all 23 Markdown files and resolved all 39 local document links. All 12 milestone IDs match the implementation plan and remain Not started. All 23 `.gitkeep` markers are empty, and leaf folders have their intended documentation or markers. The 48 files are documentation, editor/ignore configuration, or placeholders. No application code or Git initialization was introduced.

**Method:** enumerate project files with `pathlib`; parse local Markdown links and milestone/task IDs; assert target existence, marker coverage, final newlines, and the expected documentation-only file types. No dependencies were installed for this check.

**Limitations:** no application tests, dependency installs, image builds, cluster checks, version compatibility checks, or runtime resource measurements. This is not deployment evidence.

## Future record format

```text
Date / milestone:
Change being verified:
Command or scenario:
Expected result:
Observed result:
Evidence files, if any:
Limitations / remaining checks:
```

## 2026-10-24 — P01 runnable database foundation

**Change being verified:** branch `p01-database-foundation`, commits `1d1783a`..`bfe4fee` on top of baseline `07181a2`. Locked uv backend project (Python 3.13, 32 packages), `Settings.from_env()` with lab-limit validation, `Database` session lifecycle with bounded timeouts, `create_app()` lifespan, Alembic scaffolding (no revisions yet), disposable Compose PostgreSQL/RabbitMQ, Make targets, version matrix, instructor prerequisites.

**Host observed (read-only, 2026-10-23):** Apple M4 arm64, 12 CPU, 24 GiB RAM. Docker Desktop server 29.5.3 with VM memory 8321232896 bytes (~7.75 GiB) and 12 CPUs; Compose v5.1.4. Tools: git 2.54.0, uv 0.12.17, python3 3.14.2, kind v0.32.0, kubectl client v1.36.4, helm v4.3.0, GNU make 3.81, node v24.12.0, npm 11.6.2; `promtool` missing. Existing unrelated kind cluster `dso202` (kindest/node:v1.36.1, binds 127.0.0.1:80/443/30080); kube contexts `kind-dso202` (current) and `saroj`; other containers `hall-booking-local-postgres` (127.0.0.1:5433) and `document-hub-postgres-1` (0.0.0.0:5432). None were changed.

**Commands (run by the session controller on HEAD `bfe4fee`, 2026-10-24 09:11 +0600):**

| Command or scenario | Expected | Observed |
| --- | --- | --- |
| `uv lock --check --project services/backend` | Lock matches pyproject | `Resolved 32 packages` |
| `make test-unit` | Settings and guard tests pass | `37 passed` |
| `make test-deps-up` | Both dependencies healthy, loopback only | `postgres:18.6-trixie` healthy on 127.0.0.1:15432; `rabbitmq:4.3.7-management` healthy on 127.0.0.1:15672 (AMQP) and 127.0.0.1:15673 (management) |
| `make test-integration` | Migrations, session commit/rollback, timeouts, lifespan disposal, broker handshake pass against real dependencies | `7 passed` |
| `make test-integration TEST_POSTGRES_URL='...@127.0.0.1:15432/postgres?host=db.example.com'` | Destructive fixture refuses a redirected host | Every test errors at setup: "must not contain query parameters (host)" |
| `make test-deps-down` | No project containers/networks/volumes remain | 0 containers, 0 networks, 0 volumes; `dso202` and other containers still up; context still `kind-dso202` |

**TDD evidence:** settings tests failed at import (`No module named 'cloudcart.config'`) before implementation, then passed. Review-fix changes were checked by temporarily breaking each fix and observing the matching test fail (implementer report).

**Reviews:** task review (spec + quality) approved after one fix round; final whole-branch review "with fixes"; one fix wave (`bfe4fee`) and a scoped re-review.

**Limitations / remaining checks:** local tests ran on CPython 3.13.15 while the pinned image is `python:3.13.17-slim-trixie` (uv 0.12.17 cannot install 3.13.17). The libpq `tcp_user_timeout` setting is only effective on Linux; on macOS the test proves the value reaches libpq. Platform versions in `versions.yaml` are selected from primary sources but not installed or exercised; Gateway API minimum Kubernetes version and kube-prometheus-stack on Kubernetes 1.36 are `partially_verified`. No images, cluster, manifests, or dashboards exist yet. The 7.75 GiB Docker VM has not been measured against a running cluster.

## 2026-10-24 — P02 catalog, persistent carts, and access boundaries

**Change being verified:** branch `claude/p02-catalog-carts-access-875a84`, commits `c01e916` (tests) and `6f9f7c0` (implementation) on top of `1ddb042`. Catalog, identity, and cart feature modules; first Alembic revision `371b57c4f5aa`; seed command `python -m cloudcart.seed`; `CLOUDCART_COOKIE_SECURE` setting; `argon2-cffi` 25.1.0 locked (36 packages). Decisions D019–D023.

**Commands (run by the session controller on HEAD `6f9f7c0`, 2026-10-24 15:31 +0600):**

| Command or scenario | Expected | Observed |
| --- | --- | --- |
| `uv lock --check --project services/backend` | Lock matches pyproject | `Resolved 36 packages` |
| `make test-unit` | Settings (including the `cookie_secure` default) and guard tests pass | `38 passed` |
| `make test-deps-up` | Disposable dependencies healthy | PostgreSQL and RabbitMQ containers `Healthy` |
| `make test-integration TEST=services/backend/tests/integration/test_shopping.py` | Seed idempotency, catalog, persistence across two app instances, quantity validation and limits, version increments, 404/409/413/422 cases pass against PostgreSQL | `27 passed in 4.32s` |
| `make test-integration TEST=services/backend/tests/integration/test_access.py` | Guest isolation, instructor-only stock changes, CSRF 403, forged Origin / `Sec-Fetch-Site: cross-site` 403, expired guest and instructor sessions, cookie attributes, no secrets in responses or stored rows | `66 passed in 7.51s` |
| `make test-integration` | Whole integration suite passes with `filterwarnings = error` | `100 passed in 11.57s` (66 access, 1 broker, 6 database, 27 shopping) |
| Alembic round trip on a scratch database (`upgrade head`, `downgrade base`, `upgrade head`) | Tables created, removed, recreated | After upgrade: `alembic_version,cart_items,carts,guests,instructor_sessions,instructors,products`; after downgrade: `alembic_version` only; re-upgrade to `371b57c4f5aa` |
| `python -m cloudcart.seed` twice on that database with a generated 24-character password | Exit 0 both times; no duplicates | `exit 0`, `exit 0`; 8 products, 8 distinct SKUs, 1 instructor, stored hash starts `$argon2id$` |
| `python -m cloudcart.seed` with an 11-character password, then with none | Non-zero exit; message names the variable, never the value | `exit 1` both times: `cloudcart.seed: CLOUDCART_SEED_ADMIN_PASSWORD must be set to between 12 and 256 characters.` |
| `make test-deps-down` | No project containers/networks/volumes remain; other resources untouched | 0 containers, 0 networks, 0 volumes; `dso202` and the other two containers still up; context still `kind-dso202` |

The scratch database was created and dropped on the disposable test server by a controller script kept in the session scratchpad (not committed).

**TDD evidence (implementer report):** before implementation both test files failed at import (`ModuleNotFoundError: No module named 'cloudcart.seed'`) and the new unit test failed (`'Settings' object has no attribute 'cookie_secure'`). The implementer also broke each guard on purpose and saw the matching tests fail: origin check disabled → 27 access failures; CSRF check disabled → 14; cart row lock removed → the 8-way concurrent update test failed 3/3; body limit and 422 handler removed → the 413 and password-echo tests failed.

**Reviews:** task review (spec ✅, quality approved, 0 Critical/Important) and final whole-branch review ("with fixes": only this project-record update was required before merge). The final reviewer's database-free probes confirmed one DB session per request and correct 413 handling of bodies split across several ASGI messages. Seven task-review minors and three final-review minors were deferred with rulings; see [HANDOFF.md](HANDOFF.md).

**Limitations / remaining checks:** same-origin and cookie behavior was exercised with synthetic `Origin`/`Sec-Fetch-Site` headers through TestClient over `https://testserver`, not in a real browser (Task 5 Playwright). The same-origin guard relies on the gateway preserving `Host`; untested until Task 7. Argon2 memory under concurrent logins, guest-row growth, and API resource limits are unmeasured. No image, cluster, or deployment exists yet. Local tests ran on CPython 3.13.15 (image pins 3.13.17).

## 2026-10-24 — P03 atomic checkout and durable order contract

**Change being verified:** branch `claude/p03-start-ce835d`, commits `50aca8d` (tests), `e910f54` (implementation), and `bf08d29` (review-driven lock-order test) on top of `30544c8`. Orders feature module (`orders/{models,schemas,service,routes}.py`), public cart helpers `lock_guest_cart`/`clear_cart`, Alembic revision `e7b83d9b2137`, shared test helpers. No dependency changes (`uv lock --check`: 36 packages). Decisions D024–D026.

**Commands (2026-10-24, 16:40–17:12 +0600, CPython 3.13.15; final runs on HEAD `bf08d29` unless noted):**

| Command or scenario | Expected | Observed |
| --- | --- | --- |
| Baseline before changes (`make test-unit`, `make test-integration` on `30544c8`) | Green starting point | `38 passed`; `100 passed` |
| New tests before implementation (`TEST=test_checkout.py test_checkout_concurrency.py`; `TEST=test_access.py`) | Meaningful failures | Collection error `ModuleNotFoundError: No module named 'cloudcart.orders.service'`; access: `41 failed, 38 passed`, all from `relation "orders" does not exist` or 404 on `/api/v1/orders` |
| `make test-integration TEST="test_checkout.py test_checkout_concurrency.py test_access.py"` | One order, one outbox event, and one stock charge per checkout; replays 200 with the same order; reused key with another body, stale/empty cart, short stock 409; declined payment 402; trigger-forced failure after the order insert leaves no partial rows; 422 for bad keys/bodies; guessed order/receipt ids 404 for another guest | On `e910f54`: `119 passed` (35 checkout, 5 concurrency, 79 access); the sixth concurrency test, added in `bf08d29`, passed in the full run below |
| `make test-unit` | Settings, guards, and the new multi-chunk `RequestBodyLimit` tests pass | `42 passed` |
| `make test-integration` | Whole suite passes with `filterwarnings = error` | `154 passed in 20.82s` (79 access, 1 broker, 35 checkout, 6 concurrency, 6 database, 27 shopping) |
| `make test-integration TEST=test_checkout_concurrency.py` five times (before the lock-order test was added) | No flakiness in lock-wait and HTTP race tests | `5 passed` ×5 |
| Alembic on a scratch database: `upgrade head`, `alembic check`, `downgrade 371b57c4f5aa`, `downgrade base`, `upgrade head` | Models and migration agree; clean round trip | `No new upgrade operations detected.`; downgrades and re-upgrade succeed; `alembic current` = `e7b83d9b2137 (head)` |
| `make test-deps-down` | No project containers/networks/volumes remain; other resources untouched | 0 containers, 0 networks, 0 volumes; `dso202` and two unrelated containers still up; context still `kind-dso202` |

**Final-tree runs (HEAD `a03a3ae`, records only on top of `bf08d29`):** one full chain (`make test-deps-up`, `make test-unit`, `make test-integration`, `make test-deps-down`) started at 17:29 failed after about 13 minutes; its pytest summary was not captured. Docker events show both test containers healthy throughout, and the macOS power log shows the laptop entered system sleep at 17:29:18 (on battery, "Maintenance Sleep", 746 s) and woke at 17:41:44, 24 s before the run ended. The sleep interrupted the run in flight. Four reruns of the same chain with the machine awake each gave `42 passed` and `154 passed` (about 21 s), with test containers at about 3% CPU. Keep the machine awake for unattended test runs (for example `caffeinate -i make test-integration`).

**Concurrency proof:** service-level tests hold the first checkout's transaction open, poll `pg_blocking_pids` until the second transaction is blocked by the first, then commit. Last unit: the second checkout gets `InsufficientStockError` (HTTP 409); stock 0, one order, one outbox event. Same key: the waiting retry returns the committed order with `replayed=True`. A NOWAIT probe proves product locks follow id order even when the cart added the higher id first. HTTP races (2 and 6 guests on separate API instances for one unit; 5 identical same-key requests) gave exactly one 201.

**Mutation checks (implementation changed temporarily, then restored):** product lock and stock guard removed → the oversell tests failed (3); idempotency lookup moved before the cart lock → both same-key race tests failed; fingerprint comparison disabled → both key-reuse tests failed; cart not cleared → 2 failed; product lock order reversed → lock-order test failed 3/3 (ORDER BY removed: 1/3, since row order then depends on the plan); `RequestBodyLimit` keeping only the last chunk → 2 of 4 unit tests failed.

**Reviews:** final whole-branch review by a fresh reviewer: 0 Critical, 1 Important (no test enforced id-ordered product locks) fixed in `bf08d29`; five minors deferred (see [HANDOFF.md](HANDOFF.md)).

**Limitations / remaining checks:** checkout ran through TestClient and direct sessions, not a browser (Task 5). Nothing publishes outbox events yet, so `publication_pending` stays true and receipts appear only when inserted by tests (Task 4). Lock waits longer than `statement_timeout` (5 s) or an unexpected deadlock return an unhandled 500 rather than 503; a retry with the same key is safe. No image, cluster, or deployment exists yet.

## 2026-10-24 — P04 reliable publisher and fulfillment worker

**Change being verified:** branch `claude/p04-start-3c8765`, commits `a5668ca` (Celery dependency), `280476b` (failing tests), `5762706` (implementation), and `049b220` (review fix) on top of `a459ed4`. New `cloudcart.jobs` package (`celery_app`, `publisher`, `tasks`, `worker`), broker and job settings, publisher lifecycle in the API lifespan, Alembic revision `674c483b8f18`, a loopback TCP fault proxy and a worker test harness. Dependencies added: `celery 5.6.3`, `kombu 5.6.2`, `amqp 5.4.1`, `billiard 4.3.1`, `vine 5.1.0` and Celery's CLI helpers (`uv lock --check`: 50 packages). Decisions D027–D031.

**Commands (2026-10-24, 21:20–23:00 +0600, CPython 3.13.15, disposable PostgreSQL 18.6 and RabbitMQ 4.3.7):**

| Command or scenario | Expected | Observed |
| --- | --- | --- |
| New tests before implementation (`make test-unit TEST=test_settings.py`; `make test-integration TEST="test_delivery.py test_fulfillment.py"`) | Meaningful failures | Settings: `16 failed, 23 passed` (new settings missing); integration: collection error `ModuleNotFoundError: No module named 'cloudcart.jobs.celery_app'` |
| Drift test (`alembic check` through env.py) after adding model columns, before the migration | Fails | `New upgrade operations detected` (three columns, one index); passes after revision `674c483b8f18` |
| First worker runs | Worker consumes `orders` | Crash loop: RabbitMQ 4.3 refused Celery's remote-control queue (`transient_nonexcl_queues` deprecated); fixed by disabling remote control (D028) |
| Idle worker SIGTERM before the wake-up bootstep | Exit within 3 s | Failed at 9.2 s (7.3 s in a separate probe, independent of the broker timeout); passes after `PromptShutdown` |
| Review finding: worker started against a schema without `orders.fulfillment_attempts` (column renamed during the test) | Delivery requeued until the column returns; order fulfilled once | Before the fix: task acknowledged after `ProgrammingError`, order stuck `accepted` (test failed); after `049b220`: passes |
| `make test-integration TEST="test_delivery.py test_fulfillment.py"` on `5762706` | Publication, claims, faults, duplicates, crashes, retries, failure, SIGTERM, database outage | `30 passed in 48.85s` |
| Final runs on `049b220`: `make test-unit`; `make test-integration` (under `caffeinate -i`) | Whole suites with `filterwarnings = error` | `61 passed`; `186 passed in 72.50s` (12 delivery, 19 fulfillment, 7 database; the 148 earlier tests unchanged) |
| Alembic on a scratch database: `upgrade head`, `check`, `downgrade e7b83d9b2137`, `downgrade base`, `upgrade head`, `check` | Clean round trip | `No new upgrade operations detected.` twice; downgrades and re-upgrade succeed; `alembic current` = `674c483b8f18 (head)` |

**What the tests prove, from PostgreSQL rather than task return values:** each event becomes one persistent Celery protocol-2 message (`cloudcart.orders.fulfill`, task id = event id, JSON) and is marked published only after the confirm; a refused, stalled (open connection or new handshake), or unroutable (queue deleted) broker leaves events unpublished with claims released, each failure within 3× the 1 s test timeout; 40 events through two concurrent publishers give 40 distinct messages; a row lock held by another claimer is skipped, not waited on; live leases are respected and expired ones taken over; through the API with a hung broker, products, cart, and checkout answer in under 2 s and the order is published after recovery; reconnect attempts back off (3–6 connections in 3 s instead of about 30); `stop()` interrupts a 60 s idle wait in under 1 s. Worker subprocesses: processing is visible before fulfillment; two workers given the same task twice issue one receipt; a worker SIGKILLed after its commit and before its acknowledgement gets the task redelivered and the replacement changes nothing; two failing attempts are retried with backoff (≥ 0.9 s) without releasing stock; four failing attempts fail the order, return its stock once, and a late duplicate changes nothing; SIGTERM during a task finishes and acknowledges it; a PostgreSQL outage (proxy cut, ≥ 3 reconnects) leaves the order `accepted` with 0 attempts, then it is fulfilled on attempt 1; an unknown order's task is acknowledged. Service tests overlap two transactions for concurrent fulfillment and failure, and a NOWAIT probe proves stock return locks products in id order (D025).

**Mutation checks (implementation changed temporarily, then restored with git):** 15 mutations, each caught by its named test: claim without `SKIP LOCKED`; publish not `mandatory`; no publisher confirms; claims not released; no exponential backoff; leases ignored; event marked before publishing; fulfill or fail ignoring a finished status (2); order row not locked; no attempt limit; stock returned in reverse id order; failed attempt acknowledged instead of requeued; database errors not requeued. Early acknowledgement (`acks_late=False`) is not caught by the crash-after-commit test, because Celery schedules every acknowledgement on its event loop, which the solo pool runs only after a task returns; the retry test catches it (the requeue is lost).

**Reviews:** final whole-branch review by a fresh reviewer: 0 Critical, 1 Important (database errors other than lost connections acknowledged and dropped) fixed in `049b220` with a failing-first test; ten minors deferred or ruled on (see [HANDOFF.md](HANDOFF.md)).

**Limitations / remaining checks:** the worker ran as a local subprocess, not in a container or Pod; termination grace periods, probes, and image commands are Task 6/7. Faults were injected with a loopback TCP proxy, not by stopping the RabbitMQ/PostgreSQL containers; a real broker Pod outage is a Task 8 exercise. There are no metrics yet (Task 11) and no storefront (Task 5). Timing assertions (backoff counts, sub-second stops) passed on this M4 and could need wider bounds on a loaded machine.

## 2026-10-26 — P05 storefront and instructor view

**Change being verified:** branch `claude/p05-storefront-instructor-view-461e0f`, commits `d3a1796` (failing backend tests), `649641c` (instructor session/logout/order overview, version route, session guard, OpenAPI export), `e32761a` (browser tests and their API/worker harness), `45a51ad` (storefront and instructor view), and `a0ad936` (review fixes) on top of `b289a32`. No schema change (Alembic head stays `674c483b8f18`). Python: Uvicorn 0.54.0 added to the dev dependency group only (`uv.lock`: 51 packages). Node: `services/frontend/package-lock.json` (92 packages; runtime dependencies React 19.3.1, React Router 8.4.0, openapi-fetch 0.17.0, Archivo font 5.3.0; `npm audit`: 0 vulnerabilities). Decisions D032–D036.

**Commands (2026-10-24 23:30 – 2026-10-26 10:30 +0600, CPython 3.13.15, Node 24.12.0, Chromium from Playwright 1.63.0, disposable PostgreSQL 18.6 and RabbitMQ 4.3.7):**

| Command or scenario | Expected | Observed |
| --- | --- | --- |
| New backend tests before implementation (`make test-unit TEST=test_settings.py`; `TEST=test_openapi_contract.py`; `make test-integration TEST="test_admin.py test_version.py test_access.py"`) | Meaningful failures | Settings: `11 failed, 39 passed` (setting missing); OpenAPI test: `ModuleNotFoundError: No module named 'cloudcart.openapi'`; integration: `29 failed, 83 passed` (routes missing, logout not in the CSRF matrix, no session guard). One privacy test passed on a 404 and was tightened to require a 200 first |
| Existing route-inventory test after adding routes | Fails until updated | `test_openapi_documents_closed_bounded_request_schemas` listed four extra routes; inventory updated (intended contract change) |
| `make test-e2e` against a placeholder page (harness check) | Every test fails on missing UI; servers and worker start | `19 failed`: element not found or timeouts; migrations ran, API and preview served, the worker fixture consumed the queue, no processes left over. Three tests took 15–17 min because the Mac slept past midnight; later runs used `caffeinate -i` |
| First green run of the storefront | All pass | `18 passed, 1 failed`: order, receipt, and orders screens were 361–386 px wide at 360 px (route labels and items table); fixed with a vertical route, a compact items table, and single-column grids |
| Review finding tests before their fixes | Fail | Pending count with a processing order whose event is unpublished: `assert 2 == 1`; gateway 502 after the API accepted the order: generic error without "Retry order"; 403 on a cart change: no error shown and the change silently reverted |
| Final runs on the `a0ad936` tree: `make test-unit`; `make test-integration`; `make test-e2e` (under `caffeinate -i`); `npm --prefix services/frontend run build` | Whole suites green with `filterwarnings = error`; production build | `74 passed`; `220 passed in 76.75s`; `21 passed (1.5m)`; `✓ built` (JS 292 kB, 91 kB gzip) |

**What the browser tests prove (real API with its publisher, real worker subprocess, production build):** browse → cart → simulated checkout → order page reaches Fulfilled → receipt with lines and total → order history; the cart survives a reload and appears in a second tab; with the worker stopped an order shows "Queued for packing" across several polls and is fulfilled after the worker restarts; four failing attempts (worker_harness fault) show "Could not be fulfilled" and the stock returns; stale stock (stock lowered after carting) stops checkout with the API's message and a per-line warning, and checkout succeeds after lowering the quantity; a declined simulated payment keeps the cart and creates no order; a dropped connection or a 502 after the API accepted the order offers "Retry order", which reuses the key and leaves exactly one order; a refused change (403 with an unchanged session) shows the refusal instead of a new session; expired sessions (on reload and while the page is open) give a new empty cart, an empty order history, and "Order not found" for the previous order URL; a cross-site link to `GET /api/v1/session` gets 403 and the guest keeps their cart; footer versions come from the build and the API. Instructor tests: sign-in only until signed in, wrong password message, guest cookies get 401 from the admin API, stock change visible in the shop, the session survives a reload, sign-out ends it, and the counters show a backlog of two while the worker is stopped and drain after it restarts. Quality tests: axe WCAG 2.1 A/AA reports no violations on nine screens; no screen is wider than 360 px; skip link and keyboard-only add to cart.

**Mutation checks (implementation changed temporarily, then restored with git):** 9 mutations, each caught by its named test: `GET /session` without the same-origin guard; admin orders without the instructor check; logout without CSRF; `GET /admin/session` without the guard; logout deleting every instructor session; checkout retry with a new key; no session renewal after a 401; order polling that stops after one load; 4xx checkout answers treated as retryable. A first attempt at the new-key mutant did not compile (the build failed, so its test failed for the wrong reason); it was redone with compiling code and caught.

**Visual inspection:** screenshots at 1280 × 900 and 360 × 780 of the shop, cart, queued, fulfilled, and failed order pages, receipt, and instructor view. Order states, the simulated-payment panel, and both versions are legible. Two problems found and fixed: the hazard stripe of the simulated-payment panel was drawn on every edge, and the instructor tables were cramped on phones (SKU and Placed columns now hidden below 40 rem; tables scroll inside their frames).

**Reviews:** final whole-branch review by a fresh reviewer (two attempts lost to a network error and a sleeping machine; the third completed): 0 Critical; 3 Important, all fixed in `a0ad936` with failing-first tests (checkout key discarded after a gateway 5xx; renewal reported for a refusal with an unchanged session; pending-publication count including non-accepted orders, which could make "Queued" negative); six minors deferred (see [HANDOFF.md](HANDOFF.md)).

**Limitations / remaining checks:** Chromium only (no Firefox or WebKit run). The storefront ran behind `vite preview` on `http://localhost`, not behind Nginx, Traefik, or HTTPS; Secure cookies worked through Chromium's localhost exception. Serving the build from Nginx with an SPA fallback, the gateway's `Host` handling, and TLS are Task 6/7 checks. The "waiting to be queued" display was tested by marking the real order response unpublished (D036); the other states ran end to end. `npm run dev` was not exercised. Browser tests and backend integration tests cannot run at the same time (shared `orders` queue).
