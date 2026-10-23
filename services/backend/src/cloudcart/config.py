"""Runtime settings shared by the CloudCart API, worker, and migrations.

Settings come only from CLOUDCART_* environment variables. Nothing has a
credential default: every deployment supplies CLOUDCART_DATABASE_URL, e.g.
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME.
"""

from typing import Self

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ENV_PREFIX = "CLOUDCART_"
DATABASE_DRIVER = "postgresql+psycopg"


class ConfigurationError(RuntimeError):
    """CloudCart settings are missing or unsafe. The message names variables, never their values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, frozen=True)

    database_url: SecretStr
    # Zero means "wait forever" to libpq/PostgreSQL, so every timeout has a positive lower bound.
    db_connect_timeout_seconds: int = Field(default=5, ge=2, le=60)
    db_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    db_statement_timeout_ms: int = Field(default=5000, ge=100, le=600_000)

    # Bounded CPU workload for the autoscaling lab; disabled unless explicitly enabled.
    lab_enabled: bool = False
    lab_cpu_work_ms: int = Field(default=200, ge=1, le=2000)
    lab_max_concurrency: int = Field(default=2, ge=1, le=8)

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
