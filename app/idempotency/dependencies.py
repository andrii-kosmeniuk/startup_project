from typing import Annotated

from fastapi import Header, status

from app.errors import ApplicationError

EVENT_ID_HEADER = "X-Event-ID"
MAXIMUM_EVENT_ID_LENGTH = 100


def require_event_id(
    event_id: Annotated[str, Header(alias=EVENT_ID_HEADER)],
) -> str:
    normalized = event_id.strip()
    if not normalized or len(normalized) > MAXIMUM_EVENT_ID_LENGTH:
        raise ApplicationError(
            code="VALIDATION_ERROR",
            message=(
                f"{EVENT_ID_HEADER} must contain between 1 and "
                f"{MAXIMUM_EVENT_ID_LENGTH} characters"
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return normalized
