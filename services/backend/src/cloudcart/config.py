"""Runtime settings shared by the CloudCart API, worker, and migrations.

Settings come only from CLOUDCART_* environment variables. Nothing has a
credential default: every deployment supplies CLOUDCART_DATABASE_URL, e.g.
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME.
"""

from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ENV_PREFIX = "CLOUDCART_"
DATABASE_DRIVER = "postgresql+psycopg"
BROKER_SCHEMES = ("amqp", "amqps")


class ConfigurationError(RuntimeError):
    """CloudCart settings are missing or unsafe. The message names variables, never their values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, frozen=True)

    database_url: SecretStr
    # Zero means "wait forever" to libpq/PostgreSQL, so every timeout has a positive lower bound.
    db_connect_timeout_seconds: int = Field(default=5, ge=2, le=60)
    db_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    db_statement_timeout_ms: int = Field(default=5000, ge=100, le=600_000)

    # Release identifier reported by GET /api/v1/version and shown in the storefront, e.g. v1.
    release_version: str = Field(default="dev", pattern=r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")

    # Session cookies carry the Secure attribute unless a plain-HTTP setup explicitly turns it off.
    cookie_secure: bool = True

    # Bounded CPU workload for the autoscaling lab; disabled unless explicitly enabled.
    lab_enabled: bool = False
    lab_cpu_work_ms: int = Field(default=200, ge=1, le=2000)
    lab_max_concurrency: int = Field(default=2, ge=1, le=8)

    # RabbitMQ, e.g. amqp://USER:PASSWORD@HOST:5672//. The API's outbox publisher and the
    # worker need it; migrations and the seed command do not.
    broker_url: SecretStr | None = None
    # Bounds every broker connect, read, write, and publisher confirm.
    broker_timeout_seconds: int = Field(default=5, ge=1, le=60)
    publisher_enabled: bool = True
    # How long an idle publisher waits before looking for new outbox events.
    publisher_interval_ms: int = Field(default=1000, ge=100, le=60_000)
    # Simulated packing and dispatch time per order, so a backlog is observable.
    fulfillment_delay_ms: int = Field(default=1000, ge=0, le=5000)
    # First retry delay; each further retry doubles it.
    fulfillment_retry_backoff_ms: int = Field(default=1000, ge=10, le=10_000)

    @field_validator("database_url")
    @classmethod
    def _require_psycopg_postgresql_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):  # ValueError: e.g. a non-numeric port
            raise ValueError("is not a valid database URL") from None
        if url.drivername != DATABASE_DRIVER:
            raise ValueError(f"must use the {DATABASE_DRIVER}:// driver")
        return value

    @field_validator("broker_url")
    @classmethod
    def _require_amqp_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        try:
            url = urlsplit(value.get_secret_value())
            url.port  # parsing the port raises ValueError when it is not a number
        except ValueError:
            raise ValueError("is not a valid broker URL") from None
        if url.scheme not in BROKER_SCHEMES or not url.hostname:
            raise ValueError(f"must be an {' or '.join(BROKER_SCHEMES)}:// URL with a host")
        return value

    def require_broker_url(self, component: str) -> str:
        """The broker URL, or a ConfigurationError naming the variable when `component` needs it and it is missing."""
        if self.broker_url is None:
            raise ConfigurationError(
                f"Invalid CloudCart configuration: {ENV_PREFIX}BROKER_URL: required by {component}"
            )
        return self.broker_url.get_secret_value()

    @classmethod
    def from_env(cls) -> Self:
        """Load settings from the environment, raising ConfigurationError if they are invalid."""
        try:
            return cls()
        except ValidationError as error:
            message = _describe(error)
        # Raised outside the except block so neither __cause__ nor __context__ holds the
        # validation error, which contains raw input values such as the database password.
        raise ConfigurationError(message)


def _describe(error: ValidationError) -> str:
    problems = [
        f"{ENV_PREFIX}{'_'.join(str(part) for part in issue['loc']).upper()}: {issue['msg']}"
        for issue in error.errors(include_input=False, include_url=False, include_context=False)
    ]
    return "Invalid CloudCart configuration: " + "; ".join(problems)
