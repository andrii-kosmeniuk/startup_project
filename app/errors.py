from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.observability.logging import conversation_id_context, log_event


class ApplicationError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        retryable: bool = False,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details
        self.headers = headers


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    retryable: bool = False,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "conversation_id": conversation_id_context.get(),
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers=headers,
    )


async def application_error_handler(
    _: Request, error: ApplicationError
) -> JSONResponse:
    return error_response(
        code=error.code,
        message=error.message,
        status_code=error.status_code,
        retryable=error.retryable,
        details=error.details,
        headers=error.headers,
    )


async def validation_error_handler(
    _: Request, error: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "location": list(item["loc"]),
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors()
    ]
    return error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details=details,
    )


async def http_error_handler(_: Request, error: HTTPException) -> JSONResponse:
    status_codes = {
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    }
    message = error.detail if isinstance(error.detail, str) else "Request failed"
    return error_response(
        code=status_codes.get(error.status_code, "HTTP_ERROR"),
        message=message,
        status_code=error.status_code,
        retryable=error.status_code >= 500,
        details=None if isinstance(error.detail, str) else error.detail,
        headers=error.headers,
    )


async def database_error_handler(_: Request, error: SQLAlchemyError) -> JSONResponse:
    log_event("database_unavailable", error_type=type(error).__name__)
    return error_response(
        code="DATABASE_UNAVAILABLE",
        message="Database is temporarily unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        retryable=True,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
