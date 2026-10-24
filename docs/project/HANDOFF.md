# Current handoff

Updated: 2026-10-24 (Asia/Thimphu).

## Read first

1. [Project status](../../PROJECT_STATUS.md)
2. [Approved design](../superpowers/specs/2026-10-16-cloudcart-design.md)
3. [Implementation plan](../superpowers/plans/2026-10-16-cloudcart-implementation.md)
4. [Working conventions](../../CONTRIBUTING.md)
5. [Host prerequisites](../instructor/prerequisites.md) and [version matrix](../../deploy/platform/versions.yaml)

## Current state

P01 is done and verified ([evidence](VERIFICATION.md#2026-10-24--p01-runnable-database-foundation)). The instructor limited the 2026-10-23 session to P01; P02–P12 are not started and not yet authorized.

Git: `main` holds the baseline docs commit `07181a2` and all of P01; the instructor renamed the P01 branch to `main` on 2026-10-24. Remote `origin` is the public GitHub repository https://github.com/sarojsanyasicst/DSO202-K8s, so never commit credentials, personal data, or machine secrets. Commits use the instructor's GitHub noreply identity, configured locally for this repository.

What exists for later tasks to build on:

- `services/backend/` is a uv project pinned to Python `>=3.13,<3.14` with 32 locked packages. Run commands through the Make targets or `uv run --locked --project services/backend ...`.
- `cloudcart.config.Settings.from_env()` reads `CLOUDCART_*` variables. `CLOUDCART_DATABASE_URL` must be `postgresql+psycopg://...`. The bounded DB timeouts and lab settings (`lab_enabled`, `lab_cpu_work_ms`, `lab_max_concurrency`) raise `ConfigurationError` when invalid.
- `cloudcart.db.Database(settings)` exposes `session_factory` (a `sessionmaker[Session]`), `session_scope()` (commit on success, rollback and re-raise on error), and `dispose()`. `Base` has a constraint naming convention. `create_app(settings)` creates the database object in its lifespan and stores it in `app.state.database`.
- Alembic is configured with no revisions yet. Task 2 adds the first one in `services/backend/alembic/versions/`.
- Test fixtures (`services/backend/tests/conftest.py`): `test_database_url` is a fresh, migrated database for each session; `integration_settings`, `database`, `test_broker_url`, and an autouse per-test truncation with ambient-environment isolation (`tests/integration/conftest.py`). Helpers live in `tests/support.py`.
- `make test-deps-up` and `make test-deps-down` manage the `cloudcart-test` Compose project: PostgreSQL on 127.0.0.1:15432, AMQP on 127.0.0.1:15672, management on 127.0.0.1:15673.

## Next useful action

When the instructor requests it, begin P02 / Task 2: write the failing PostgreSQL integration tests `test_shopping.py` and `test_access.py`, then catalog, identity, and cart models, the first Alembic revision, and the idempotent seed command. Choose and lock the password hashing library in that task.

## Carried-forward notes

- **Task 2:** per-test truncation empties every application table, including rows a migration might insert. Seed through `python -m cloudcart.seed`, as planned, not through migrations.
- **Task 6:**
  - Add Uvicorn together with the API launch command (it was deliberately removed from P01). Refresh its versions.yaml entry; `verified_by` still cites an earlier uv.lock resolution.
  - Add the production-mode setting that rejects the lab endpoint.
  - libpq `tcp_user_timeout` only takes effect on Linux, which is fine for the containers.
- **Task 7:**
  - Normalize the versions.yaml schema (exact vs range fields; kubectl is `v1.36.x`; helm is pinned at v4.3.1 while v4.3.0 is installed) before preflight reads it.
  - Close the `partially_verified` edges: Gateway API minimum Kubernetes version, and kube-prometheus-stack on 1.36.
  - Consider an advisory lock for migration Jobs.
  - Size the DB pool against PostgreSQL `max_connections` across replicas.
- **Instructor decisions pending:**
  - Ratify the D014 version matrix in [DECISIONS.md](DECISIONS.md).
  - Docker Desktop VM memory: ~7.75 GiB observed, against the 12–14 GiB planning estimate. Increase it before P07, or measure and accept it.
  - Optional: upgrade uv so local tests can run CPython 3.13.17, the same patch as the image (they currently use 3.13.15).
- **Host hygiene:** uv's interpreter store now holds CPython 3.15.0rc2 (unused) and 3.13.15. A `~/.local/bin/python3.13` link was added. Remove them only if the instructor wants.
- `promtool` is missing; it is needed for P11 rule tests.

## Known constraints and open inputs

- Apple M4, 24 GB RAM; kind target is 1 control plane + 2 workers. An unrelated kind cluster `dso202` exists and owns 127.0.0.1:80/443. Never modify or delete it. The current context is `kind-dso202`, so always name `kind-cloudcart` explicitly.
- Students receive prebuilt images; CI/image-building instruction stays outside classroom scope.
- Argo CD needs a reachable Git source in P10. The public `origin` repository is a candidate; the instructor confirms the URL, revision, and values path then.
- Baseline exclusions are unchanged: no real payment/shipping, object storage, Redis, extra business microservices, centralized logs/tracing, or stateful HA.

## Verification and continuation hygiene

Record runtime checks in [VERIFICATION.md](VERIFICATION.md), update the milestone board, append the session log, and replace this handoff with the actual next continuation point.
