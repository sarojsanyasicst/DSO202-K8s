# Backend and worker

Python package: `src/cloudcart/`. It contains the settings, database lifecycle, FastAPI app factory, and the catalog, identity, and cart features. Orders, the outbox publisher, and the Celery worker arrive with later tasks; the API and worker will share domain models and business logic but run separately.

| Folder | Responsibility |
| --- | --- |
| `src/cloudcart/catalog/` | Products, prices, inventory |
| `src/cloudcart/identity/` | Guest sessions and instructor authentication |
| `src/cloudcart/cart/` | Persistent carts |
| `src/cloudcart/orders/` | Transactional checkout, order ownership, receipts |
| `src/cloudcart/jobs/` | Outbox publication and fulfillment tasks |
| `alembic/versions/` | Database revisions |
| `tests/unit/` | Focused tests without external services |
| `tests/integration/` | PostgreSQL/RabbitMQ behavior and API contracts |

The P01 foundation provides `config.py` (validated `CLOUDCART_*` settings), `db.py` (engine, bounded timeouts, `Database.session_scope()`, the per-request `DbSession` dependency), `main.py` (`create_app(settings)` with engine lifecycle, routers, and the request-body limit), the Alembic environment (`alembic.ini`, `alembic/env.py`), and locked dependencies in `pyproject.toml`/`uv.lock`. P02 added the first revision, the catalog/identity/cart routes under `/api/v1`, and `seed.py`. The access rules (sessions, cookies, CSRF, same-origin checks, cart limits) are decisions D019–D023 in [DECISIONS.md](../../docs/project/DECISIONS.md). Orders, jobs, and launch commands are added by later tasks in the [implementation plan](../../docs/superpowers/plans/2026-10-16-cloudcart-implementation.md).

Seed a migrated database (idempotent; the instructor password comes from a Secret in deployments):

```sh
CLOUDCART_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME \
CLOUDCART_SEED_ADMIN_PASSWORD='at-least-12-characters' \
  uv run --locked --project services/backend python -m cloudcart.seed
```

Run tests from the repository root:

```sh
make test-unit
make test-deps-up        # disposable PostgreSQL and RabbitMQ from tests/compose.yaml
make test-integration    # TEST=services/backend/tests/integration/test_database.py narrows the run
make test-deps-down
```

Integration tests create a fresh database per pytest session, apply `alembic upgrade head`, and empty application tables after each test. They only run against loopback test services.
