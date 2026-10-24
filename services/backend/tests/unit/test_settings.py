import os

import pytest

from cloudcart.config import ConfigurationError, Settings

TEST_PASSWORD = "unit-test-secret-7f3a"
VALID_DATABASE_URL = f"postgresql+psycopg://cloudcart:{TEST_PASSWORD}@127.0.0.1:5432/cloudcart"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Start every test without CLOUDCART_* settings inherited from the shell or Make."""
    for name in list(os.environ):
        if name.startswith("CLOUDCART_"):
            monkeypatch.delenv(name)
    return monkeypatch


def test_settings_rejects_missing_database_url() -> None:
    with pytest.raises(ConfigurationError, match="CLOUDCART_DATABASE_URL"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CLOUDCART_LAB_CPU_WORK_MS", "0"),
        ("CLOUDCART_LAB_CPU_WORK_MS", "-1"),
        ("CLOUDCART_LAB_CPU_WORK_MS", "2001"),
        ("CLOUDCART_LAB_CPU_WORK_MS", "1000000"),
        ("CLOUDCART_LAB_MAX_CONCURRENCY", "0"),
        ("CLOUDCART_LAB_MAX_CONCURRENCY", "-2"),
        ("CLOUDCART_LAB_MAX_CONCURRENCY", "9"),
        ("CLOUDCART_LAB_MAX_CONCURRENCY", "unlimited"),
    ],
)
def test_settings_rejects_unsafe_lab_limits(
    isolated_environment: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv(variable, value)

    with pytest.raises(ConfigurationError, match=variable):
        Settings.from_env()


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CLOUDCART_DB_CONNECT_TIMEOUT_SECONDS", "0"),
        ("CLOUDCART_DB_CONNECT_TIMEOUT_SECONDS", "61"),
        ("CLOUDCART_DB_POOL_TIMEOUT_SECONDS", "0"),
        ("CLOUDCART_DB_POOL_TIMEOUT_SECONDS", "61"),
        ("CLOUDCART_DB_STATEMENT_TIMEOUT_MS", "0"),
        ("CLOUDCART_DB_STATEMENT_TIMEOUT_MS", "600001"),
    ],
)
def test_settings_rejects_unbounded_database_timeouts(
    isolated_environment: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv(variable, value)

    with pytest.raises(ConfigurationError, match=variable):
        Settings.from_env()


def test_settings_defaults_keep_lab_disabled_and_timeouts_bounded(
    isolated_environment: pytest.MonkeyPatch,
) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)

    settings = Settings.from_env()

    assert settings.database_url.get_secret_value() == VALID_DATABASE_URL
    assert settings.lab_enabled is False
    assert settings.lab_cpu_work_ms == 200
    assert settings.lab_max_concurrency == 2
    assert settings.db_connect_timeout_seconds == 5
    assert settings.db_pool_timeout_seconds == 5
    assert settings.db_statement_timeout_ms == 5000


def test_settings_default_to_secure_cookies(isolated_environment: pytest.MonkeyPatch) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)

    assert Settings.from_env().cookie_secure is True

    isolated_environment.setenv("CLOUDCART_COOKIE_SECURE", "false")

    assert Settings.from_env().cookie_secure is False


def test_settings_accept_lab_limits_at_their_bounds(isolated_environment: pytest.MonkeyPatch) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_LAB_ENABLED", "true")
    isolated_environment.setenv("CLOUDCART_LAB_CPU_WORK_MS", "2000")
    isolated_environment.setenv("CLOUDCART_LAB_MAX_CONCURRENCY", "8")

    settings = Settings.from_env()

    assert settings.lab_enabled is True
    assert settings.lab_cpu_work_ms == 2000
    assert settings.lab_max_concurrency == 8


@pytest.mark.parametrize(
    "database_url",
    [
        f"mysql://cloudcart:{TEST_PASSWORD}@127.0.0.1/cloudcart",
        f"postgresql://cloudcart:{TEST_PASSWORD}@127.0.0.1/cloudcart",
        f"postgresql+psycopg://cloudcart:{TEST_PASSWORD}@127.0.0.1:not-a-port/cloudcart",
        f"not a url {TEST_PASSWORD}",
    ],
)
def test_configuration_error_never_echoes_database_secrets(
    isolated_environment: pytest.MonkeyPatch, database_url: str
) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", database_url)

    with pytest.raises(ConfigurationError, match="CLOUDCART_DATABASE_URL") as raised:
        Settings.from_env()

    assert TEST_PASSWORD not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_settings_repr_hides_database_url(isolated_environment: pytest.MonkeyPatch) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)

    assert TEST_PASSWORD not in repr(Settings.from_env())


VALID_BROKER_URL = f"amqp://cloudcart:{TEST_PASSWORD}@127.0.0.1:5672//"


def test_settings_default_to_publishing_with_bounded_job_timings(isolated_environment: pytest.MonkeyPatch) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)

    settings = Settings.from_env()

    assert settings.broker_url is None
    assert settings.publisher_enabled is True
    assert settings.broker_timeout_seconds == 5
    assert settings.publisher_interval_ms == 1000
    assert settings.fulfillment_delay_ms == 1000
    assert settings.fulfillment_retry_backoff_ms == 1000


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CLOUDCART_BROKER_TIMEOUT_SECONDS", "0"),
        ("CLOUDCART_BROKER_TIMEOUT_SECONDS", "61"),
        ("CLOUDCART_PUBLISHER_INTERVAL_MS", "99"),
        ("CLOUDCART_PUBLISHER_INTERVAL_MS", "60001"),
        ("CLOUDCART_FULFILLMENT_DELAY_MS", "-1"),
        ("CLOUDCART_FULFILLMENT_DELAY_MS", "5001"),
        ("CLOUDCART_FULFILLMENT_RETRY_BACKOFF_MS", "9"),
        ("CLOUDCART_FULFILLMENT_RETRY_BACKOFF_MS", "10001"),
    ],
)
def test_settings_reject_unbounded_job_timings(
    isolated_environment: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv(variable, value)

    with pytest.raises(ConfigurationError, match=variable):
        Settings.from_env()


def test_settings_accept_job_timings_at_their_bounds(isolated_environment: pytest.MonkeyPatch) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_BROKER_TIMEOUT_SECONDS", "60")
    isolated_environment.setenv("CLOUDCART_PUBLISHER_INTERVAL_MS", "100")
    isolated_environment.setenv("CLOUDCART_FULFILLMENT_DELAY_MS", "5000")
    isolated_environment.setenv("CLOUDCART_FULFILLMENT_RETRY_BACKOFF_MS", "10")

    settings = Settings.from_env()

    assert (settings.broker_timeout_seconds, settings.publisher_interval_ms) == (60, 100)
    assert (settings.fulfillment_delay_ms, settings.fulfillment_retry_backoff_ms) == (5000, 10)


@pytest.mark.parametrize("broker_url", [VALID_BROKER_URL, f"amqps://cloudcart:{TEST_PASSWORD}@broker.internal:5671/shop"])
def test_settings_accept_amqp_broker_urls(isolated_environment: pytest.MonkeyPatch, broker_url: str) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_BROKER_URL", broker_url)

    settings = Settings.from_env()

    assert settings.broker_url is not None and settings.broker_url.get_secret_value() == broker_url
    assert TEST_PASSWORD not in repr(settings)


@pytest.mark.parametrize(
    "broker_url",
    [
        f"redis://cloudcart:{TEST_PASSWORD}@127.0.0.1:6379/0",
        f"memory://cloudcart:{TEST_PASSWORD}@localhost/",
        f"amqp://cloudcart:{TEST_PASSWORD}@",
        f"not a url {TEST_PASSWORD}",
    ],
)
def test_settings_reject_non_amqp_broker_urls_without_echoing_them(
    isolated_environment: pytest.MonkeyPatch, broker_url: str
) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_BROKER_URL", broker_url)

    with pytest.raises(ConfigurationError, match="CLOUDCART_BROKER_URL") as raised:
        Settings.from_env()

    assert TEST_PASSWORD not in str(raised.value)


@pytest.mark.parametrize("value", ["v1", "v2", "1.4.0", "v2.0.0-rc.1", "dev", "2026.10.24+build.7"])
def test_settings_accepts_release_versions(isolated_environment: pytest.MonkeyPatch, value: str) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_RELEASE_VERSION", value)

    assert Settings.from_env().release_version == value


@pytest.mark.parametrize("value", ["", "v 1", "v1<script>", "x" * 65, "v1/../v2"])
def test_settings_rejects_unsafe_release_versions(isolated_environment: pytest.MonkeyPatch, value: str) -> None:
    isolated_environment.setenv("CLOUDCART_DATABASE_URL", VALID_DATABASE_URL)
    isolated_environment.setenv("CLOUDCART_RELEASE_VERSION", value)

    with pytest.raises(ConfigurationError, match="CLOUDCART_RELEASE_VERSION"):
        Settings.from_env()
