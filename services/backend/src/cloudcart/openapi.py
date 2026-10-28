"""Print the API's OpenAPI document; the storefront generates its TypeScript API types from it.

`make frontend-types` runs `python -m cloudcart.openapi` and writes the result to
services/frontend/src/api/openapi.json. Building the document needs no database or broker.
"""

import json
from typing import Any

from pydantic import SecretStr

from cloudcart.config import Settings
from cloudcart.main import create_app

# Never connected to: the lifespan, which would open the engine, does not run while exporting.
PLACEHOLDER_DATABASE_URL = "postgresql+psycopg://openapi@localhost/openapi"


def openapi_document() -> dict[str, Any]:
    settings = Settings(database_url=SecretStr(PLACEHOLDER_DATABASE_URL), publisher_enabled=False)
    return create_app(settings).openapi()


if __name__ == "__main__":
    print(json.dumps(openapi_document(), indent=2, sort_keys=True))
