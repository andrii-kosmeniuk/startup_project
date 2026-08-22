import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_ENVIRONMENT_VARIABLE = "API_KEY"
MINIMUM_API_KEY_LENGTH = 16

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="Shared API key used by n8n to call FastAPI.",
    auto_error=False,
)


def get_configured_api_key() -> str:
    api_key = os.getenv(API_KEY_ENVIRONMENT_VARIABLE, "")
    if len(api_key.strip()) < MINIMUM_API_KEY_LENGTH:
        raise RuntimeError(
            f"{API_KEY_ENVIRONMENT_VARIABLE} must be configured with at least "
            f"{MINIMUM_API_KEY_LENGTH} characters"
        )
    return api_key


def validate_api_key_configuration() -> None:
    get_configured_api_key()


def require_api_key(provided_api_key: str | None = Security(api_key_header)) -> None:
    configured_api_key = get_configured_api_key()
    if provided_api_key is None or not secrets.compare_digest(
        provided_api_key, configured_api_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key",
                "retryable": False,
            },
            headers={"WWW-Authenticate": "ApiKey"},
        )
