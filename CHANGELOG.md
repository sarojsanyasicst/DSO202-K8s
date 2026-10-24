# Changelog

## Unreleased

### Added

- P01 backend foundation: locked Python 3.13 uv project, validated environment settings with bounded lab limits, database session lifecycle with bounded timeouts, FastAPI app factory, and Alembic scaffolding.
- Disposable PostgreSQL 18.6 and RabbitMQ 4.3.7 test dependencies (`tests/compose.yaml`) with `make test-unit`, `test-integration`, `test-deps-up`, and `test-deps-down`.
- Unit and PostgreSQL/RabbitMQ integration tests for settings, sessions, timeouts, migrations, and test-fixture safety.
- Version matrix (`deploy/platform/versions.yaml`) and instructor host prerequisites (`docs/instructor/prerequisites.md`).
- Approved CloudCart architecture and a 12-task implementation plan.
- Project folders for application code, containers, deployments, monitoring, scripts, tests, teaching material, and generated artifacts.
- A milestone status board, roadmap, decision log, session history, verification record, and next-session handoff.
- Working conventions and ignore rules for local/generated material.

No application release has been built or deployed.
