"""Run the CloudCart API and worker for the storefront's browser tests, and adjust their TEST-ONLY database.

The storefront's Playwright configuration calls this script through `uv run`; the application never
imports it. Every command uses the disposable dependencies named by CLOUDCART_TEST_POSTGRES_URL and
CLOUDCART_TEST_BROKER_URL (`make test-e2e` exports them) and the database `cloudcart_e2e` on that server.

    serve-api --port N --release R   recreate and migrate cloudcart_e2e, seed it, empty the orders
                                     queue, then serve the API (publisher enabled) on 127.0.0.1:N
    worker --delay-ms N [--failing-attempts N]
                                     run the fulfillment worker against cloudcart_e2e; with
                                     --failing-attempts, through worker_harness.py's TEST-ONLY fault
    queue-consumers                  print the number of consumers on the orders queue
    reset-catalog                    restore every seeded product's stock and price
    set-stock SKU N                  set one product's stock
    expire-guest-sessions            expire every guest session, as if seven days had passed

The instructor password comes from CLOUDCART_E2E_ADMIN_PASSWORD (a TEST-ONLY value the browser tests own).
Do not run the browser tests together with backend integration tests: both use the orders queue.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import uvicorn
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.jobs import worker
from cloudcart.main import create_app
from cloudcart.seed import PRODUCTS, seed_database
from jobs_support import orders_queue_state, purge_orders_queue
from support import (
    BROKER_URL_VARIABLE,
    POSTGRES_URL_VARIABLE,
    require_loopback,
    require_no_libpq_routing_overrides,
    required_environment,
    without_ambient_settings,
)

E2E_DATABASE = "cloudcart_e2e"
ADMIN_PASSWORD_VARIABLE = "CLOUDCART_E2E_ADMIN_PASSWORD"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
CONNECT_TIMEOUT_SECONDS = 3
MIGRATION_TIMEOUT_SECONDS = 120
# Publish quickly so tests do not wait on the default one-second idle interval.
PUBLISHER_INTERVAL_MS = 200


def server_url() -> URL:
    url = make_url(required_environment(POSTGRES_URL_VARIABLE))
    require_loopback(POSTGRES_URL_VARIABLE, url.host, url.query)
    require_no_libpq_routing_overrides()
    return url


def database_url() -> str:
    return server_url().set(database=E2E_DATABASE).render_as_string(hide_password=False)


def broker_url() -> str:
    url = required_environment(BROKER_URL_VARIABLE)
    parts = urlsplit(url)
    require_loopback(BROKER_URL_VARIABLE, parts.hostname, parse_qs(parts.query))
    return url


def settings(**overrides: object) -> Settings:
    """Settings from a clean environment: ambient CLOUDCART_* values never reach the e2e API or worker."""
    environment = without_ambient_settings(os.environ)
    environment["CLOUDCART_DATABASE_URL"] = database_url()
    environment["CLOUDCART_BROKER_URL"] = broker_url()
    for name, value in overrides.items():
        environment[f"CLOUDCART_{name.upper()}"] = str(value)
    os.environ.clear()
    os.environ.update(environment)
    return Settings.from_env()


def recreate_database() -> None:
    server = create_engine(
        server_url(),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        with server.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{E2E_DATABASE}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{E2E_DATABASE}"'))
    finally:
        server.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        env={**without_ambient_settings(os.environ), "CLOUDCART_DATABASE_URL": database_url()},
        timeout=MIGRATION_TIMEOUT_SECONDS,
        check=True,
    )


def run_statement(statement: str, **parameters: object) -> None:
    database = Database(settings())
    try:
        with database.engine.begin() as connection:
            connection.execute(text(statement), parameters)
    finally:
        database.dispose()


def serve_api(port: int, release: str) -> None:
    admin_password = required_environment(ADMIN_PASSWORD_VARIABLE)
    recreate_database()
    api_settings = settings(publisher_interval_ms=PUBLISHER_INTERVAL_MS, release_version=release)
    database = Database(api_settings)
    try:
        with database.session_scope() as session:
            seed_database(session, admin_password)
    finally:
        database.dispose()
    purge_orders_queue(broker_url())
    uvicorn.run(create_app(api_settings), host="127.0.0.1", port=port, log_level="warning")


def run_worker(delay_ms: int, failing_attempts: int) -> None:
    settings(fulfillment_delay_ms=delay_ms, fulfillment_retry_backoff_ms=100)
    if failing_attempts:
        # worker_harness reads its fault settings when imported.
        os.environ["CLOUDCART_TEST_FAILING_ATTEMPTS"] = str(failing_attempts)
        import worker_harness  # noqa: F401
    worker.main()


def reset_catalog() -> None:
    for product in PRODUCTS:
        run_statement(
            "UPDATE products SET stock = :stock, price_cents = :price_cents WHERE sku = :sku",
            stock=product["stock"],
            price_cents=product["price_cents"],
            sku=product["sku"],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve-api")
    serve.add_argument("--port", type=int, required=True)
    serve.add_argument("--release", required=True)
    run = commands.add_parser("worker")
    run.add_argument("--delay-ms", type=int, default=0)
    run.add_argument("--failing-attempts", type=int, default=0)
    commands.add_parser("queue-consumers")
    commands.add_parser("reset-catalog")
    stock = commands.add_parser("set-stock")
    stock.add_argument("sku")
    stock.add_argument("stock", type=int)
    commands.add_parser("expire-guest-sessions")
    arguments = parser.parse_args()

    match arguments.command:
        case "serve-api":
            serve_api(arguments.port, arguments.release)
        case "worker":
            run_worker(arguments.delay_ms, arguments.failing_attempts)
        case "queue-consumers":
            print(orders_queue_state(broker_url())[1])
        case "reset-catalog":
            reset_catalog()
        case "set-stock":
            run_statement(
                "UPDATE products SET stock = :stock WHERE sku = :sku", stock=arguments.stock, sku=arguments.sku
            )
        case "expire-guest-sessions":
            run_statement("UPDATE guests SET expires_at = now() - interval '1 second'")


if __name__ == "__main__":
    main()
