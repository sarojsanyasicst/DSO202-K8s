# CloudCart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a working local e-commerce application and a Kubernetes teaching kit ending with monitoring metrics.

**Architecture:** React storefront, modular FastAPI backend with a managed outbox publisher, Celery worker, PostgreSQL, and RabbitMQ. Establish application correctness before packaging the five components for kind, then add Helm, Argo CD, and Prometheus/Grafana.

**Tech Stack:** React, TypeScript, FastAPI, SQLAlchemy, Alembic, psycopg, Celery/Kombu, PostgreSQL, RabbitMQ, pytest, Playwright, kind, Calico, Traefik/Gateway API, Helm, Argo CD, Metrics Server, kube-prometheus-stack.

**Spec:** [Approved design](../specs/2026-10-16-cloudcart-design.md). Read both documents before implementation.

## Global Constraints

- The target is a local kind cluster with one control-plane node and two worker nodes on an Apple M4 MacBook Pro with 24 GB RAM.
- Students act as the Kubernetes operations team; CI and image-building instruction are outside the teaching scope.
- All runtime dependencies run locally in that cluster. Argo CD additionally needs a reachable Git source during the GitOps lesson.
- Start with frontend=2, API=2, worker=1, PostgreSQL=1, and RabbitMQ=1.
- The API HPA may scale from two to four replicas, subject to a measured resource budget. Scale the worker manually from one to three replicas.
- Provide ARM64 application images; AMD64 variants are conditional on the student distribution target. Pin release images and infrastructure versions; no mutable latest tags.
- Use single-instance stateful workloads and node-local storage; explicitly document the absence of cross-node storage failover and physical failure-domain isolation.
- The course ends with reading and explaining metrics under load and controlled failure. Basic logs/events support troubleshooting; centralized logging, tracing, alert routing, stateful HA, and worker queue-based autoscaling are outside the baseline.
- Start by evaluating a Docker VM allocation around 12–14 GiB; measure before treating this estimate as sufficient. Prometheus initial retention target is 24 hours, with a size cap and Alertmanager disabled.
- No real payment, shipping service, object store, Redis result backend, customer registration, or additional business microservices.
- Keep the existing approved documents. This directory is currently not a Git repository; initialize version control at execution, not while planning. Do not publish a repository or alter an existing cluster without an execution request covering it.

## Review Focus

1. Two guests buying the final item simultaneously must not oversell; Task 3 tests concurrent PostgreSQL transactions.
2. Checkout retries with the same key must not charge stock twice; Task 3 tests identical and conflicting request payloads.
3. A publisher dying after broker confirmation, or a worker dying after its DB commit, must not duplicate fulfillment; Task 4 tests both crash boundaries with real dependencies.
4. A guessed order URL or forged instructor action must not expose another guest's data or change state; Task 2 and Task 5 test ownership, authorization, and same-origin protections.
5. Multi-replica metrics and CPU load must remain interpretable on kind; Task 9 verifies bounded HPA load, and Task 11 verifies business-gauge deduplication and bounded labels.

## File ownership and interfaces

All paths below are relative to the project root. Group Python by business feature; do not introduce a generic repository/service framework.

| Path | Responsibility |
| --- | --- |
| `services/backend/pyproject.toml`, `services/backend/uv.lock` | Locked Python runtime and test dependencies |
| `services/backend/src/cloudcart/config.py`, `db.py`, `main.py` | Settings, DB/session lifecycle, FastAPI startup/shutdown |
| `services/backend/src/cloudcart/{catalog,identity,cart,orders}/` | Feature models, request/response schemas, routes, transactions |
| `services/backend/src/cloudcart/jobs/{publisher,celery_app,tasks}.py` | Outbox publication, task transport, idempotent fulfillment |
| `services/backend/src/cloudcart/{metrics,health,lab,seed}.py` | Instrumentation, probes, bounded lab workload, seed command |
| `services/backend/alembic/` | Versioned PostgreSQL migrations |
| `services/backend/tests/{unit,integration}/` | Focused business, transport, and health tests |
| `services/frontend/` | React application, locked npm dependencies, browser tests |
| `tests/compose.yaml`, `tests/conftest.py` | Disposable test dependencies and shared acceptance helpers |
| `containers/{backend,frontend}.Dockerfile` | Non-root release images |
| `deploy/kind/`, `deploy/plain/`, `deploy/platform/` | kind config, teaching manifests, pinned infrastructure settings |
| `deploy/helm/cloudcart/`, `deploy/gitops/` | Equivalent application chart and Argo CD definitions |
| `monitoring/{dashboards,rules,tests}/` | Provisioned dashboards, recording rules, executable query checks |
| `scripts/` | Prerequisite checks, image packaging, bootstrap, acceptance, bounded traffic, lab resets |
| `docs/{handoff,instructor,students}/` | Software-team contract and teaching materials |

Shared types: UUID IDs; timezone-aware UTC timestamps; integer minor currency units with currency fixed to USD for seed data. `OrderStatus = Literal['accepted', 'processing', 'fulfilled', 'failed']`. `OrderView` in `orders/schemas.py` contains `id: UUID`, `status: OrderStatus`, `publication_pending: bool`, `total_cents: int`, `created_at: datetime`, and `receipt_available: bool`. `CartView` in `cart/schemas.py` contains `id: UUID`, `version: int`, `items: list[CartItemView]`, and `total_cents: int`; each item has `product_id: UUID`, `quantity: int`, and `unit_price_cents: int`. `FulfillmentResult` in `orders/schemas.py` contains `order_id: UUID`, `status: OrderStatus`, `receipt_id: UUID | None`, and `already_applied: bool`. API responses never expose guest session tokens, password hashes, or raw exception traces.

API contract: `/api/v1/products`, `/api/v1/session`, `/api/v1/cart`, `/api/v1/orders`, `/api/v1/orders/{id}`, `/api/v1/orders/{id}/receipt`, `/api/v1/admin/login`, `/api/v1/admin/orders`, `/api/v1/admin/products/{id}/stock`; `/health/live`, `/health/ready`, `/metrics`, `/api/v1/version`. State-changing routes require CSRF protection; checkout additionally requires `Idempotency-Key`. Define exact OpenAPI request schemas in the owning task and generate frontend types from that schema.

Use one Uvicorn process per API Pod and one Celery solo worker process per worker Pod. This makes each Pod an observable scaling unit and avoids accidental metric duplication across Python subprocesses. Task execution and dependency calls are bounded; do not rely on prefork-only soft timeouts in solo mode.

## Task 1: Runnable database foundation

**Files:** Create `Makefile`, `.gitignore`, `services/backend/pyproject.toml`, `services/backend/uv.lock`, `services/backend/src/cloudcart/{__init__,config,db,main}.py`, `services/backend/alembic.ini`, `services/backend/alembic/env.py`, `tests/compose.yaml`, `services/backend/tests/conftest.py`, `services/backend/tests/unit/test_settings.py`, `deploy/platform/versions.yaml`, `docs/instructor/prerequisites.md`.

**Interfaces:** `Settings.from_env() -> Settings`; `create_app(settings: Settings) -> FastAPI`; `session_scope() -> Iterator[Session]`; `make test-unit`, `make test-integration`, `make test-deps-up`, `make test-deps-down`. Test targets invoke `uv run --project services/backend pytest`, accept `TEST=path`, and default to their unit/integration directory respectively. Integration fixtures read explicit test-only dependency settings, apply Alembic migrations, and isolate test data. Test dependencies expose PostgreSQL on 15432 and RabbitMQ on 15672 (AMQP), with management on 15673. Runtime credentials are explicit inputs, never real credentials committed to Git.

- [x] Write `test_settings_rejects_missing_database_url` and `test_settings_rejects_unsafe_lab_limits`; assert missing DB configuration and negative/unbounded lab settings raise configuration errors.
- [x] Run `uv run --project services/backend pytest services/backend/tests/unit/test_settings.py -q`; confirm collection/import failure before implementation.
- [x] Implement settings, synchronous SQLAlchemy sessions with bounded connection timeouts, app factory, Alembic setup, and disposable Compose dependencies. Define Make targets; generate the Python lockfile. Record exact compatible stable versions, ARM64 image availability, source links, and checked date in `versions.yaml`; include PostgreSQL/RabbitMQ and all platform charts/controllers, not only application dependencies.
- [x] Run `make test-unit` and `make test-deps-up`; verify tests pass and both disposable dependencies become healthy. Record available tools, Docker allocation, current contexts, and existing clusters without changing them. Initialize Git only if still absent, and commit these explicit files plus approved documents as the foundation.

## Task 2: Catalog, persistent carts, and access boundaries

**Files:** Create `services/backend/src/cloudcart/catalog/{models,schemas,routes}.py`, `identity/{models,schemas,routes,security}.py`, `cart/{models,schemas,routes,service}.py`, `seed.py`, first Alembic revision, `services/backend/tests/integration/test_shopping.py`, `test_access.py`; modify `main.py`.

**Interfaces:** `ensure_guest(session: Session, token: str | None) -> GuestSession`; `set_cart_item(session: Session, guest_id: UUID, product_id: UUID, quantity: int) -> CartView`; `seed_database(session: Session, admin_password: str) -> None`. Session tokens are cryptographically random and only hashed values are persisted. Guest and instructor cookies are HTTP-only, secure in HTTPS mode, and same-site; a session-bound CSRF token is returned separately. Cart responses include an integer `version` used during checkout.

- [x] Write PostgreSQL integration tests asserting seed reruns do not duplicate products, cart changes survive a new API instance, negative/zero/over-limit quantities are rejected, guest B cannot access guest A's resources, instructor login is required for stock changes, and missing/incorrect CSRF tokens return 403. Include forged Origin and expired session cases.
- [x] Run `make test-integration TEST=services/backend/tests/integration/test_shopping.py` and the equivalent command for `test_access.py`; confirm failure due to missing endpoints/models.
- [x] Implement catalog/cart/session endpoints and instructor stock updates. Add minimal migrations and idempotent seed command `python -m cloudcart.seed`. Use a maintained password hashing library selected and locked here. Enforce request size and field limits; reject unknown products and empty carts predictably.
- [x] Re-run the two files; require all assertions to pass against PostgreSQL, not SQLite. Commit only this task's files and lockfile changes.

## Task 3: Atomic checkout and durable order contract

**Files:** Create `services/backend/src/cloudcart/orders/{models,schemas,routes,service}.py`, next Alembic revision, `services/backend/tests/integration/test_checkout.py`, `test_checkout_concurrency.py`; extend `test_access.py` and register routes in `main.py`.

**Interfaces:** `checkout(session: Session, guest_id: UUID, cart_version: int, payment_outcome: Literal['approved','declined'], idempotency_key: str) -> CheckoutResult`; `get_order(session: Session, guest_id: UUID, order_id: UUID) -> OrderView`. `CheckoutResult` contains `order: OrderView` and `replayed: bool`. One durable outbox row references the order; `(guest_id, idempotency_key)` and receipt `order_id` are unique DB constraints. Guest order lists are session-scoped.

- [x] Add tests with these exact assertions: successful checkout creates one order/outbox event and decrements stock once; identical key/body returns the same order, including simultaneous requests; reused key/different body returns 409; stale cart version returns 409; a declined simulated payment returns 402 without changing stock; transaction rollback leaves no partial order/outbox. Run two independent DB connections against stock=1 and assert exactly one success, one 409, and stock=0. Add guessed order/receipt ID tests returning 404 for another guest.
- [x] Run `make test-integration TEST=services/backend/tests/integration/test_checkout.py` and `TEST=services/backend/tests/integration/test_checkout_concurrency.py`; confirm meaningful failures.
- [x] Implement checkout with server-side prices, deterministic stock-row locking order, guarded inventory updates, request fingerprinting for idempotency, and an outbox insert in the same transaction. Look up completed idempotency requests before checking the now-cleared cart. Return 201 initially and 200 for a replay. Add order/history/receipt reads.
- [x] Run all three affected test files; prove rollback and concurrency behavior. Commit the checkout slice.

## Task 4: Reliable publisher and fulfillment worker

**Files:** Create `services/backend/src/cloudcart/jobs/{__init__,publisher,celery_app,tasks}.py`, `services/backend/tests/integration/test_delivery.py`, `test_fulfillment.py`; modify `main.py` and order models/migrations where necessary.

**Interfaces:** `publish_batch(session_factory: Callable[[], Session], limit: int = 20) -> int`; `publish_order(order_id: UUID, event_id: UUID, enqueued_at: datetime) -> None`; `fulfill_order(session: Session, order_id: UUID) -> FulfillmentResult`; Celery task name `cloudcart.orders.fulfill`, durable queue `orders`, JSON serialization only. Start/stop the publisher thread through FastAPI lifespan with an interruptible wait. Use `event_id` as task ID; it is not a deduplication guarantee.

- [ ] Add tests for broker outage retaining unpublished events while product reads and checkout remain usable; two publishers claiming concurrently; confirmation followed by publisher crash; duplicate/concurrent task delivery; worker crash after committed fulfillment; retry exhaustion; and graceful termination during a task. Assert one receipt, one final business transition, and no repeated stock mutation. Terminal processing failure returns reserved stock exactly once; a retried transient failure does not release it prematurely.
- [ ] Run `make test-integration TEST=services/backend/tests/integration/test_delivery.py` and `TEST=services/backend/tests/integration/test_fulfillment.py`; require failing behavior before adding transport/worker code.
- [ ] Implement publisher locking/claims and confirmed persistent publication through Celery/Kombu so task serialization matches Celery. Bound broker calls and reconnect backoff; mark published only after a confirmed, routable send. Configure late acknowledgement, prefetch=1, connection-loss/worker-loss behavior, and at most three retries with exponential backoff. Bound demo processing delay to 0–5 seconds. Keep a business failure record in PostgreSQL when retries end.
- [ ] Run both integration files using real PostgreSQL/RabbitMQ and a worker subprocess. Introduce dependency faults only inside the disposable test environment. Assert recovery within test timeouts and inspect durable state independently of task return values. Commit the processing slice.

## Task 5: Usable storefront and instructor view

**Files:** Create `services/frontend/package.json`, npm lockfile, `src/{main,App,api}.tsx`, `src/features/{catalog,cart,orders,admin}/`, `src/styles.css`, `public/products/`, `tests/shop.spec.ts`, `playwright.config.ts`; add OpenAPI type-generation command to `Makefile`.

**Interfaces:** Use the backend OpenAPI contract; keep session cookies same-origin. Screens: product grid, cart, simulated checkout, order history/detail/receipt, instructor login and inventory/orders. Display version and pending-publication/processing/failure states. Poll active order status every two seconds; stop polling when terminal or unmounted.

- [ ] Write browser tests for browse→cart→checkout→fulfilled receipt; reload preserving the cart; stopping a worker leaving an accepted/processing order visible; error messages for stale stock and payment decline; instructor access restrictions; and expired session recovery without exposing a previous guest's data.
- [ ] Run `npm --prefix services/frontend run test:e2e`; establish failing pages/flows against the Task 4 test services.
- [ ] Implement a coherent responsive storefront with keyboard-accessible controls, labelled forms, empty/loading/error states, bounded uploads disabled, and product placeholder assets stored in the repository. Keep simulated payment prominent. Generate API types; avoid duplicating Python schemas manually.
- [ ] Run browser tests and a production frontend build. Inspect desktop and narrow-screen rendering; confirm operational states and version are legible. Commit the frontend slice.

## Task 6: Versioned images and software-team handoff

**Files:** Create `containers/{backend,frontend}.Dockerfile`, `.dockerignore`, `services/backend/src/cloudcart/{health,lab}.py`, `scripts/images.sh`, `scripts/check-images.sh`, `docs/handoff/{application-contract,release-notes}.md`; add health/version tests.

**Interfaces:** API port 8000; frontend 8080; worker health/metrics server 9101. Backend image commands launch API, worker, migration, or seed mode. `scripts/images.sh build --release v1 --platform linux/arm64`, `export --release v1 --output artifacts/images`, and later `load --cluster cloudcart --release v1`. Track exact tags/digests/checksums in `artifacts/releases/v1.json`; image archives are generated artifacts, ignored by Git.

- [ ] Add tests proving live checks stay healthy during DB/broker outage, API readiness fails without DB but succeeds without broker, production mode rejects the lab workload endpoint, and the version endpoint returns the baked release version. Define worker probes against process/event-loop health rather than a broker-dependent `celery inspect ping`; idle, busy, reconnecting, and stopped worker conditions must be covered.
- [ ] Run affected unit/integration tests and confirm failure before implementing health/lab/version behavior.
- [ ] Implement non-root images, bounded graceful shutdown, and runtime configuration. Bake v1/v2 version identifiers and a visible storefront release change using reproducible build arguments; both releases keep a compatible schema. Provide a readiness-failure configuration for the rollback lesson. Implement an instructor-authorized lab CPU endpoint with server-side work bounds and concurrency cap, disabled by default. Document every environment setting, image command, port, probe, dependency, and metric contract.
- [ ] Build and smoke-test ARM64 v1 and v2 images; verify user identity, versions, dependency reconnection, and archive import. AMD64 build is conditional, never falsely report it tested. Commit sources and release manifests, not archives or local credentials.

## Task 7: kind infrastructure and plain-manifest deployment

**Files:** Create `deploy/kind/cloudcart.yaml`, `deploy/platform/{calico,traefik,metrics-server}.yaml`, `deploy/plain/{namespace,config,services,postgres,rabbitmq,frontend,api,worker,migrations,seed,gateway}.yaml`, `scripts/{preflight,bootstrap,acceptance}.sh`, `docs/instructor/local-access.md`.

**Interfaces:** Cluster/context `cloudcart`/`kind-cloudcart`; namespace `cloudcart`; Deployments `cloudcart-frontend`, `cloudcart-api`, `cloudcart-worker`; StatefulSets `cloudcart-postgres`, `cloudcart-rabbitmq`. Commands: `scripts/bootstrap.sh --cluster cloudcart`, `scripts/acceptance.sh smoke --context kind-cloudcart`. Bind host ports 8080/8443 to loopback; use `https://localhost:8443` as baseline, avoiding an automatic hosts-file change. Certificate SAN includes localhost. Document optional custom shop hostname and certificate trust setup without automatically changing the OS trust store.

- [ ] Implement preflight first: tool/version checks, available memory/ports, ARM64 compatibility, and detection of an already-existing cluster. An occupied name/port must report the conflict, never silently delete a cluster. Validate config against the selected versions before creation.
- [ ] Bootstrap the isolated named kind cluster with the default CNI disabled, install the pinned Calico/Gateway API/Traefik versions, verify local dynamic PVC provisioning, and load both application releases onto all eligible nodes. Install Metrics Server and verify its API; any lab-only kubelet certificate workaround must be narrowly scoped and documented.
- [ ] Deploy DB/broker and wait for readiness, run migration and idempotent seed Jobs to completion, then deploy the three app components and route. Secrets are created from instructor inputs/local ignored files; examples contain placeholders. Use exact image tags and `IfNotPresent` for imported images. Expose database and broker only internally.
- [ ] Run `scripts/acceptance.sh smoke --context kind-cloudcart`; require three Ready nodes, bound claims, expected replica counts, HTTPS product→checkout→fulfillment, and observable version. Record measured idle memory/CPU. Commit configs/scripts/docs after checking generated secret material is excluded.

## Task 8: Security, persistence, rollout, and recovery exercises

**Files:** Create `deploy/plain/{network-policies,rbac,pdb}.yaml`, `scripts/check-policies.sh`, `docs/students/{01-deploy,02-configure,03-recover}.md`, `docs/instructor/failure-runbook.md`; modify workload probe/security/resource/topology settings.

**Interfaces:** `scripts/acceptance.sh policies|persistence|rollout|backlog --context kind-cloudcart`; all scenarios restore a named known-good configuration. Use explicit node selectors/topology spread to place app replicas on workers; demonstrate the PDB on API replicas. Disable ServiceAccount token automount for app Pods; give student read permissions only where needed.

- [ ] Run negative connectivity checks before policy installation and record that the test Pod can currently connect; then install default-deny/allow policies and require the same forbidden connection to fail while API/worker/DNS/monitoring paths still work. Test denial of Secret reads using impersonation or an equivalent limited account.
- [ ] Configure bounded resource requests/limits, probes, non-root contexts, graceful termination, replica spread, and API PDB. Verify stateless replacement, DB Pod replacement retaining the same seeded/order data, compatible v2 rollout, failed-readiness rollout, and rollback to v1.
- [ ] Run worker-stop/backlog/worker-scale recovery and RabbitMQ outage/outbox recovery separately. Preserve RabbitMQ node identity and PVC. Compare unique order/receipt counts before and after; verify stock remains consistent. Explain stateful node-local storage behavior and PDB limits in the exercise observations.
- [ ] Run the four acceptance scenarios once after changes. Every exercise must include actions, expected UI behavior, observations, recovery, and pass criteria. Commit this operations slice; do not add a separate unit test merely mirroring YAML.

## Task 9: Controlled load and CPU autoscaling

**Files:** Create `deploy/plain/api-hpa.yaml`, `scripts/traffic.py`, `tests/test_traffic_limits.py`, `docs/students/04-scale.md`; extend `scripts/acceptance.sh`.

**Interfaces:** `scripts/traffic.py --scenario browsing|orders|cpu --url URL --duration SECONDS --concurrency N`; require explicit duration <=300 seconds, concurrency <=20, and a shutdown deadline. CPU scenario requires lab mode and instructor session. HPA uses API CPU requests, min=2/max=4; begin with 60% utilization and tune only if measured evidence requires it.

- [ ] Write `test_rejects_unbounded_duration`, `test_rejects_excess_concurrency`, `test_cpu_requires_lab_authorization`, and `test_stop_deadline`; assert the runner exits within its deadline and cleans up workers. Run the focused test file and confirm failure before implementation.
- [ ] Implement deterministic bounded traffic and the HPA; document the server-side CPU work bound separately from traffic duration. Demonstrate worker replica scaling independently, with HPA disabled for workers.
- [ ] Run `scripts/acceptance.sh autoscaling --context kind-cloudcart`; require resource metrics available, API scale-up above two, replicas never above four, healthy checkout during load, and eventual scale-down after the configured stabilization period. Capture elapsed times and peak usage; record actual machine limits rather than promising fixed scaling latency.
- [ ] Verify lab mode can be disabled and remains disabled in normal release values. Commit traffic, HPA, tests, and measured instructions.

## Task 10: Helm equivalence and GitOps ownership

**Files:** Create `deploy/helm/cloudcart/{Chart.yaml,values.yaml,values.schema.json,templates/}`, `deploy/gitops/{project,application}.yaml`, `deploy/platform/argocd.yaml`, `scripts/{check-rendered,handoff}.sh`, `docs/students/05-helm-gitops.md`, `docs/instructor/git-source.md`.

**Interfaces:** Chart `cloudcart` renders all five application components, Services, ConfigMap, PVC templates, Jobs, route, security policies, PDB, and optional HPA. Credentials are externally created Secrets referenced by name. GitOps inputs are repository URL, revision, chart path `deploy/helm/cloudcart`, and values path; never invent a repository or publish without authorization. Release Jobs use uniquely revisioned names and documented Argo sync order; handle immutable Job specs on repeat sync.

- [ ] Render the chart and compare semantic fields against plain manifests using `scripts/check-rendered.sh`; require identical ports, replicas, image tags, environment contracts, storage, routing, and network rules for the same settings. Reject missing Secrets, empty repository settings, and invalid HPA limits. Run `helm lint` and Kubernetes server dry-run with necessary CRDs installed.
- [ ] Implement Helm packaging and a documented transition helper with an explicit `--reset-demo-data` flag. Capture a PostgreSQL dump before each destructive teaching reset, retain it outside deleted PVCs, and require an unmistakable target context/namespace. The exercise deliberately reseeds demo data; do not silently discard data or claim migration continuity. Remove previous deployment ownership before reinstalling the chart.
- [ ] Install the chart locally and run smoke acceptance. Configure the pinned single-instance Argo CD installation; render templates while repository input is absent. Once the instructor supplies a reachable source, verify repo access, transition ownership, and require Synced/Healthy. If the source is unavailable, report GitOps validation pending; do not claim it was tested.
- [ ] Demonstrate declared v1→v2→v1 revision changes and drift repair. Ensure HPA-owned replicas do not create endless GitOps drift, and replica experiments use Git configuration once Argo CD owns the app. Re-run smoke acceptance and commit packaging/docs.

## Task 11: Metrics and three provisioned dashboards

**Files:** Create `services/backend/src/cloudcart/metrics.py`, `services/backend/tests/integration/test_metrics.py`, `deploy/platform/{monitoring,postgres-exporter}.yaml`, chart monitoring templates, `monitoring/dashboards/{kubernetes,application,dependencies}.json`, `monitoring/rules/cloudcart.yaml`, `monitoring/tests/cloudcart.test.yaml`, `scripts/check-monitoring.sh`, `docs/students/06-monitor.md`.

**Interfaces:** HTTP counters/histograms use route templates, method, and outcome. Worker exposes port 9101 and emits processing/queue-wait histograms plus completion/retry/failure attempt counters. Queue wait is first task start minus its publish-attempt timestamp; accepted-to-first-start delay is a distinct observation. The API exposes DB-derived `cloudcart_orders{status}` and `cloudcart_outbox_pending`; use `max` across replicas for these shared business gauges, not `sum`. Expose runtime metrics even during DB failure and separately indicate dependency collection failure.

- [ ] Write integration tests asserting HTTP route labels contain no IDs, broker outage increases durable pending-publication count, duplicated deliveries leave unique fulfilled-order count unchanged, worker retry attempts differ from unique business outcomes, and two API replicas report equivalent DB gauges without doubling dashboard totals. Run `make test-integration TEST=services/backend/tests/integration/test_metrics.py`; confirm missing instrumentation fails.
- [ ] Implement instrumentation, RabbitMQ Prometheus plugin, PostgreSQL exporter, and ServiceMonitors/PodMonitors. Configure correct label selectors, monitoring namespace access, non-public metrics endpoints, and scrape resource limits. Install a trimmed pinned kube-prometheus-stack: one Prometheus, 24h retention, initial 2GiB retention size/5GiB PVC, Alertmanager disabled, suitable kube-state/kubelet collectors. Disable unsupported kind control-plane/node exporters; retain useful container metrics. Provision Grafana dashboards from source.
- [ ] Write recording-rule fixtures for API rate/error ratio/p95, unique order counts, queue backlog, and replica health. Run `promtool test rules monitoring/tests/cloudcart.test.yaml`; assert `max` business gauges and `sum` per-instance counters produce expected results. Validate dashboard JSON and every referenced metric against actual scrapes.
- [ ] Run `scripts/check-monitoring.sh --context kind-cloudcart`, then replay browsing, CPU, backlog, and broker-outage traffic. Require expected scrape targets up, three dashboards populated, observed backlog growth/drain, no unexplained missing panels, and measured resource usage within the configured VM budget. Re-run Helm render checks for optional monitoring resources. Commit the monitoring slice.

## Task 12: Rehearsed teaching kit and release artifacts

**Files:** Create `README.md`, `docs/handoff/student-handoff.md`, `docs/instructor/{course-guide,verification-record}.md`, `docs/students/README.md`, `scripts/rehearse.sh`; update release manifests, runbooks, and exercises from measured results.

**Interfaces:** `scripts/rehearse.sh --context kind-cloudcart` runs the existing acceptance scenarios in teaching order with bounded waits and explicit reset points. It must refuse an unrelated context. Generated evidence belongs in ignored `artifacts/verification/`; sanitized results belong in the verification record. All public instructions link to files that exist.

- [ ] Review the complete spec against the implemented deliverables. Provide the student handoff as a software-team delivery: source tree, Dockerfiles, prebuilt image archives/checksums, release notes, configuration contract, health/metrics contract, and troubleshooting entry points. Keep build machinery in instructor material; students start from supplied images.
- [ ] Run focused backend/integration/browser tests, frontend build, Helm lint/render checks, and Prometheus rule tests once for the final release. Broaden testing only if a failure/change introduces a new concern.
- [ ] Rehearse from a clean project-owned cluster on the actual M4, including manual deployment, TLS, policies, persistence, rollout/rollback, outage recovery, autoscaling, Helm, reachable-source GitOps, and dashboards. Capture durations, CPU/memory, observed limitations, and release versions. A missing Git source or unavailable Docker means that gate remains pending, not passed.
- [ ] Confirm cleanup commands target only project-owned resources and require explicit flags for PVC/cluster deletion. Verify archives import on the target architecture, Secrets are absent from tracked files, and no user account/cloud service is required for application execution. Commit the teaching kit and report achieved versus pending acceptance gates without publishing remotely.

## Self-review and execution boundary

Spec coverage: application behavior Tasks 1–5; image/software-team delivery Task 6/12; platform/routing/storage Task 7/8; scale/load Task 9; packaging/GitOps Task 10; metrics Task 11; teaching proof and measured laptop budget Task 12. All five Review Focus conditions map to explicit assertions. Task signatures and endpoint names above are the cross-task contract; revise downstream consumers when intentionally changing them.

Planning creates documentation only. No test command in this document has been run against an implemented application, and no version matrix, memory requirement, or end-to-end deployment has yet been validated. The next action is plan review and selection of an execution method, not automatic infrastructure installation.

## Primary references for implementers

- [Publisher confirms and consumer acknowledgements](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ reliability and duplicate delivery](https://www.rabbitmq.com/docs/reliability)
- [Celery worker pools and solo-mode limitations](https://docs.celeryq.dev/en/stable/userguide/workers.html)
- [Prometheus instrumentation](https://prometheus.io/docs/practices/instrumentation/)
- [Metric label naming and cardinality](https://prometheus.io/docs/practices/naming/)
- Platform installation and monitoring references are in the approved design. Recheck official compatibility documentation before choosing exact versions.
