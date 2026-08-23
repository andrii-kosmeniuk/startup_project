from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.observability.logging import (
    application_logger,
    conversation_id_context,
    request_id_context,
)

CONVERSATION_ID_HEADER = "X-Conversation-ID"
REQUEST_ID_HEADER = "X-Request-ID"
MAXIMUM_CONVERSATION_ID_LENGTH = 100


def _get_conversation_id(request: Request) -> str | None:
    conversation_id = request.headers.get(CONVERSATION_ID_HEADER)
    return conversation_id.strip() if conversation_id is not None else None


def _conversation_id_error(conversation_id: str | None) -> JSONResponse | None:
    if conversation_id is None or (
        conversation_id and len(conversation_id) <= MAXIMUM_CONVERSATION_ID_LENGTH
    ):
        return None
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": (
                "X-Conversation-ID must contain between 1 and "
                f"{MAXIMUM_CONVERSATION_ID_LENGTH} characters"
            )
        },
    )


@contextmanager
def _request_context(request_id: str, conversation_id: str | None) -> Iterator[None]:
    request_token = request_id_context.set(request_id)
    conversation_token = conversation_id_context.set(conversation_id or None)
    try:
        yield
    finally:
        conversation_id_context.reset(conversation_token)
        request_id_context.reset(request_token)


def _add_correlation_headers(
    response: Response, request_id: str, conversation_id: str | None
) -> None:
    response.headers[REQUEST_ID_HEADER] = request_id
    if conversation_id:
        response.headers[CONVERSATION_ID_HEADER] = conversation_id


def _log_request_completed(
    request: Request, status_code: int, started_at: float
) -> None:
    application_logger.info(
        "request_completed",
        extra={
            "event": "http_request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        },
    )


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = f"req_{uuid4().hex}"
        conversation_id = _get_conversation_id(request)
        started_at = perf_counter()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        with _request_context(request_id, conversation_id):
            try:
                response = _conversation_id_error(conversation_id)
                if response is None:
                    response = await call_next(request)
                status_code = response.status_code
                _add_correlation_headers(response, request_id, conversation_id)
                return response
            except Exception:
                application_logger.exception(
                    "request_failed",
                    extra={"event": "http_request_failed"},
                )
                raise
            finally:
                _log_request_completed(request, status_code, started_at)
