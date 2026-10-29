import os
from typing import Optional

from loguru import logger
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from open_notebook.config import DEFAULT_MAX_UPLOAD_SIZE_MB


def get_max_upload_size_bytes() -> Optional[int]:
    """Configured max request body size, in bytes, or None for no cap.

    Read from OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB on every call (see
    open_notebook.config for the default). Unset, blank, zero, negative or
    malformed values all mean unlimited, so a PDF of any size is accepted
    by default; only a positive number installs a cap (413 above it).
    """
    raw = os.environ.get("OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB", "").strip()
    if not raw:
        return (
            None
            if DEFAULT_MAX_UPLOAD_SIZE_MB is None
            else int(DEFAULT_MAX_UPLOAD_SIZE_MB * 1024 * 1024)
        )
    try:
        mb = float(raw)
    except ValueError:
        logger.warning(
            f"OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB={raw!r} is not a number; "
            "uploads are uncapped"
        )
        return None
    if mb <= 0:
        return None
    return int(mb * 1024 * 1024)


class _RequestBodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    """
    Raw ASGI middleware rejecting requests whose body exceeds a configured
    maximum, so a large upload can't exhaust memory/disk on a deployment
    with no fronting proxy enforcing its own limit (e.g. the shipped
    docker-compose.yml, which exposes the API directly).

    Implemented at the raw ASGI level (not BaseHTTPMiddleware) so the check
    can run ahead of FastAPI's own body/form parsing instead of after it.
    Rejects on the `Content-Length` header up front when present (the common
    case, and cheap), and also counts bytes as the body streams in - a
    client can lie about Content-Length or omit it entirely with chunked
    transfer-encoding.

    Pass max_body_size=None to disable enforcement entirely (the default):
    the middleware then passes requests straight through.
    """

    def __init__(self, app: ASGIApp, max_body_size: Optional[int]) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_body_size is None:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_size:
                    logger.warning(
                        f"Rejected {scope.get('method', '?')} {scope.get('path', '?')}: "
                        f"declared body of {content_length} bytes exceeds the "
                        f"{self.max_body_size}-byte limit"
                    )
                    await _send_413(send)
                    return
            except ValueError:
                pass  # malformed header - fall through to streaming enforcement

        total_size = 0
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def receive_wrapper() -> Message:
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                total_size += len(message.get("body") or b"")
                if total_size > self.max_body_size:
                    raise _RequestBodyTooLarge()
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except _RequestBodyTooLarge:
            logger.warning(
                f"Rejected {scope.get('method', '?')} {scope.get('path', '?')}: "
                f"streamed body exceeded the {self.max_body_size}-byte limit"
            )
            if not response_started:
                await _send_413(send)
            # Else the app already started responding - nothing safe to send;
            # let the connection drop rather than violate the ASGI protocol
            # with a second response.start.


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"detail":"Request body exceeds the maximum allowed upload size"}',
        }
    )
