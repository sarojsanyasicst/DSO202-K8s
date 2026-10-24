"""Alembic environment for CloudCart.

Migrations run online against CLOUDCART_DATABASE_URL, using the same settings
validation and bounded connection/statement timeouts as the API and worker.
Raise CLOUDCART_DB_STATEMENT_TIMEOUT_MS for the migration process if a future
revision legitimately needs longer statements.
"""

from logging.config import fileConfig

from alembic import context

import cloudcart.cart.models  # noqa: F401
import cloudcart.catalog.models  # noqa: F401
import cloudcart.identity.models  # noqa: F401
import cloudcart.orders.models  # noqa: F401
from cloudcart.config import Settings
from cloudcart.db import Base, Database

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Feature modules register their tables on Base.metadata when imported. Import
# each model module above when it is added so `alembic revision --autogenerate`
# sees it.
target_metadata = Base.metadata


def run_migrations_online() -> None:
    database = Database(Settings.from_env())
    try:
        with database.engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.dispose()


if context.is_offline_mode():
    raise SystemExit("CloudCart migrations run online only; offline SQL generation is not configured.")

run_migrations_online()
