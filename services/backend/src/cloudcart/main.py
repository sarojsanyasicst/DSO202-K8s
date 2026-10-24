"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cloudcart.cart.routes import router as cart_router
from cloudcart.catalog.routes import router as catalog_router
from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.identity.routes import router as identity_router

API_PREFIX = "/api/v1"
MAX_REQUEST_BODY_BYTES = 16 * 1024


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
    app.add_middleware(RequestBodyLimit, max_bytes=MAX_REQUEST_BODY_BYTES)
    app.add_exception_handler(RequestValidationError, _validation_error)
    for router in (catalog_router, identity_router, cart_router):
        app.include_router(router, prefix=API_PREFIX)
    return app


async def _validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 body without the rejected input, so errors never echo submitted passwords."""
    issues = [{key: value for key, value in issue.items() if key != "input"} for issue in error.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(issues)})


class RequestBodyLimit:
    """Answer 413 for request bodies over `max_bytes` before any route reads or parses them.

    Bodies are buffered up to the limit, so chunked uploads without Content-Length are
    bounded too; the route then receives the buffered body.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":  # the client disconnected
                return
            body += message.get("body", b"")
            if len(body) > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            more_body = message.get("more_body", False)

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413, content={"detail": f"Request body exceeds {self.max_bytes} bytes."}
        )
        await response(scope, receive, send)
