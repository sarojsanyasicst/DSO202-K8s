# CloudCart developer commands. Keep this file compatible with GNU make 3.81
# (the macOS default): no .ONESHELL, grouped targets, or newer functions.

.DEFAULT_GOAL := help
.PHONY: help test-unit test-integration test-deps-up test-deps-down frontend-types test-e2e

BACKEND_DIR := services/backend
FRONTEND_DIR := services/frontend
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
	@echo "make frontend-types    Export the API's OpenAPI document and regenerate the storefront API types"
	@echo "make test-e2e          Run storefront browser tests against the API, a worker, and the test dependencies (TEST=spec to narrow)"

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

# The storefront's API types are generated from the API's own OpenAPI document; a backend
# unit test fails when the committed document no longer matches the API.
frontend-types:
	uv run --locked --project $(BACKEND_DIR) python -m cloudcart.openapi > $(FRONTEND_DIR)/src/api/openapi.json.tmp
	mv $(FRONTEND_DIR)/src/api/openapi.json.tmp $(FRONTEND_DIR)/src/api/openapi.json
	npm --prefix $(FRONTEND_DIR) run generate:api

# Builds the storefront, then starts the API (fresh cloudcart_e2e database) and a worker
# against the disposable dependencies. Do not run it while backend integration tests run:
# both use the broker's orders queue.
test-e2e:
	CLOUDCART_TEST_POSTGRES_URL='$(TEST_POSTGRES_URL)' \
	CLOUDCART_TEST_BROKER_URL='$(TEST_BROKER_URL)' \
	npm --prefix $(FRONTEND_DIR) run test:e2e $(if $(TEST),-- $(TEST),)
