"""The storefront's generated API types come from the committed OpenAPI document; it must match the API."""

import json
from pathlib import Path

from cloudcart.openapi import openapi_document

COMMITTED_DOCUMENT = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "openapi.json"


def test_committed_openapi_document_matches_the_api() -> None:
    assert COMMITTED_DOCUMENT.is_file(), "Generate it with `make frontend-types`."
    committed = json.loads(COMMITTED_DOCUMENT.read_text())

    assert committed == openapi_document(), "The API changed; regenerate with `make frontend-types`."


def test_openapi_document_names_the_storefront_routes() -> None:
    paths = openapi_document()["paths"]

    for path in (
        "/api/v1/version",
        "/api/v1/admin/session",
        "/api/v1/admin/logout",
        "/api/v1/admin/orders",
    ):
        assert path in paths
