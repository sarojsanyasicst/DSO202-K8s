# CloudCart developer commands. Keep this file compatible with GNU make 3.81
# (the macOS default): no .ONESHELL, grouped targets, or newer functions.

.DEFAULT_GOAL := help
.PHONY: help test-unit test-integration test-deps-up test-deps-down

BACKEND_DIR := services/backend
PYTEST := uv run --locked --project $(BACKEND_DIR) pytest

# Disposable test dependencies. The explicit Compose project name keeps these
# containers apart from every other Compose project on the host.
TEST_COMPOSE := docker compose --project-name cloudcart-test --file tests/compose.yaml
TEST_DEPS_WAIT_SECONDS := 180

# TEST-ONLY connection settings for the loopback-bound containers defined in
# tests/compose.yaml. They are not deployment credentials.
TEST_POSTGRES_URL := postgresql+psycopg://cloudcart_test:cloudcart_test_only@127.0.0.1:15432/postgres
TEST_BROKER_URL := amqp://cloudcart_test:cloudcart_test_only@127.0.0.1:15672//

help:
	@echo "make test-unit         Run backend unit tests (TEST=path to narrow)"
	@echo "make test-deps-up      Start disposable PostgreSQL and RabbitMQ; wait until healthy"
	@echo "make test-integration  Run backend integration tests against them (TEST=path to narrow)"
	@echo "make test-deps-down    Remove the disposable test containers and their data"

test-unit:
	$(PYTEST) $(if $(TEST),$(TEST),$(BACKEND_DIR)/tests/unit)

test-integration:
	CLOUDCART_TEST_POSTGRES_URL='$(TEST_POSTGRES_URL)' \
	CLOUDCART_TEST_BROKER_URL='$(TEST_BROKER_URL)' \
	$(PYTEST) $(if $(TEST),$(TEST),$(BACKEND_DIR)/tests/integration)

test-deps-up:
	$(TEST_COMPOSE) up --detach --wait --wait-timeout $(TEST_DEPS_WAIT_SECONDS)

test-deps-down:
	$(TEST_COMPOSE) down --volumes --remove-orphans
