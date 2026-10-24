"""RequestBodyLimit on raw ASGI messages: chunked bodies are buffered, bounded, and replayed whole."""

import asyncio

from starlette.types import Message, Receive, Scope, Send

from cloudcart.main import RequestBodyLimit

LIMIT = 10


class RecordingApp:
    """The wrapped application: records the body it reads and answers 204."""

    def __init__(self) -> None:
        self.bodies: list[bytes] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        body, more_body = b"", True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        self.bodies.append(body)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def call(messages: list[Message], headers: list[tuple[bytes, bytes]] | None = None) -> tuple[RecordingApp, int | None]:
    """Send `messages` through the middleware; return the wrapped app and the response status."""
    app = RecordingApp()
    pending = list(messages)
    sent: list[Message] = []

    async def receive() -> Message:
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "PUT", "path": "/", "headers": headers or []}
    asyncio.run(RequestBodyLimit(app, max_bytes=LIMIT)(scope, receive, send))
    status = next((message["status"] for message in sent if message["type"] == "http.response.start"), None)
    return app, status


def chunks(*parts: bytes) -> list[Message]:
    return [
        {"type": "http.request", "body": part, "more_body": index < len(parts) - 1} for index, part in enumerate(parts)
    ]


def test_chunks_within_the_limit_reach_the_app_as_one_body() -> None:
    app, status = call(chunks(b"abc", b"", b"defg", b"hij"))

    assert status == 204
    assert app.bodies == [b"abcdefghij"]


def test_chunks_that_together_exceed_the_limit_are_rejected_before_the_app_runs() -> None:
    app, status = call(chunks(b"abcd", b"efgh", b"ijk"))

    assert status == 413
    assert app.bodies == []


def test_declared_oversized_length_is_rejected_without_reading_the_body() -> None:
    app, status = call(chunks(b"tiny"), headers=[(b"content-length", str(LIMIT + 1).encode())])

    assert status == 413
    assert app.bodies == []


def test_client_disconnect_mid_body_never_reaches_the_app() -> None:
    app, status = call([{"type": "http.request", "body": b"abc", "more_body": True}])

    assert status is None
    assert app.bodies == []
