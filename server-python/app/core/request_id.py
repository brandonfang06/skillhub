import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"
MESSAGE_REQUEST_ID_FIELD = "skillhub.request_id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_current_request_id: ContextVar[str | None] = ContextVar("skillhub_request_id", default=None)


def is_valid_request_id(value: str | None) -> bool:
    return value is not None and REQUEST_ID_PATTERN.fullmatch(value) is not None


def current_request_id() -> str | None:
    return _current_request_id.get()


def request_id_from_request(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if is_valid_request_id(request_id) else None


@contextmanager
def request_id_scope(value: str | None) -> Iterator[None]:
    if value is not None and not is_valid_request_id(value):
        raise ValueError("Invalid request ID")
    token = _current_request_id.set(value)
    try:
        yield
    finally:
        _current_request_id.reset(token)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not is_valid_request_id(request_id):
            request_id = str(uuid4())
        request.state.request_id = request_id

        with request_id_scope(request_id):
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response

