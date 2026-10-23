"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cloudcart.config import Settings
from cloudcart.db import Database


def create_app(settings: Settings) -> FastAPI:
    """Build the API. The database engine lives exactly as long as the application's lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        app.state.database = database
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(title="CloudCart", lifespan=lifespan)
    app.state.settings = settings
    return app
