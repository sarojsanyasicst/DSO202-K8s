# Backend and worker

Python package: `src/cloudcart/`. This directory hosts FastAPI, feature modules, the outbox publisher, and the Celery worker. API and worker share domain models and business logic but run separately.

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

The P01 foundation provides `config.py` (validated `CLOUDCART_*` settings), `db.py` (engine, bounded timeouts, `Database.session_scope()`), `main.py` (`create_app(settings)` with engine lifecycle), the Alembic environment (`alembic.ini`, `alembic/env.py`; no revisions yet), and locked dependencies in `pyproject.toml`/`uv.lock`. Feature modules and launch commands are added by later tasks in the [implementation plan](../../docs/superpowers/plans/2026-10-16-cloudcart-implementation.md).

Run tests from the repository root:

```sh
make test-unit
make test-deps-up        # disposable PostgreSQL and RabbitMQ from tests/compose.yaml
make test-integration    # TEST=services/backend/tests/integration/test_database.py narrows the run
make test-deps-down
```

Integration tests create a fresh database per pytest session, apply `alembic upgrade head`, and empty application tables after each test. They only run against loopback test services.
