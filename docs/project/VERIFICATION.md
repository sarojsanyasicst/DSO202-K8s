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
