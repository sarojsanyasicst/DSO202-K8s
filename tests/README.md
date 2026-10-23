# Shared acceptance testing

`compose.yaml` defines the disposable, loopback-only PostgreSQL and RabbitMQ used by backend integration tests (`make test-deps-up` / `make test-deps-down`). Shared acceptance helpers and traffic-runner checks will be added here later. Backend tests live in `services/backend/tests/`; frontend browser tests live in `services/frontend/tests/`; Prometheus rule tests live in `monitoring/tests/`.

Recorded test runs and their results are kept in [VERIFICATION.md](../docs/project/VERIFICATION.md).
