# Backend and worker

Planned Python package: `src/cloudcart/`. This directory will host FastAPI, feature modules, the outbox publisher, and the Celery worker. API and worker share domain models and business logic but run separately.

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

No Python package, dependencies, migration environment, or launch commands exist yet. Add them with P01 in the [implementation plan](../../docs/superpowers/plans/2026-10-16-cloudcart-implementation.md).
