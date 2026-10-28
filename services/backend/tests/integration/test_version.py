"""The release version the storefront shows next to its own."""

from cloudcart.config import Settings
from helpers import OpenClient


def test_version_defaults_to_dev(open_client: OpenClient) -> None:
    response = open_client().get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {"version": "dev"}


def test_version_reports_the_configured_release(open_client: OpenClient, integration_settings: Settings) -> None:
    release = integration_settings.model_copy(update={"release_version": "v2"})

    response = open_client(release).get("/api/v1/version")

    assert response.json() == {"version": "v2"}
