from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.calls import service
from app.calls.schemas import CallOutcome, CallOutcomeCreate
from app.data.database import get_db
from app.security.api_key import require_api_key
from app.errors import ApplicationError

router = APIRouter(
    prefix="/call-outcomes",
    tags=["call outcomes"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=CallOutcome, status_code=status.HTTP_201_CREATED)
def create_call_outcome(
    request: CallOutcomeCreate,
    session: Session = Depends(get_db),
    conversation_id: str | None = Header(default=None, alias="X-Conversation-ID"),
) -> CallOutcome:
    if conversation_id is not None and conversation_id.strip() != request.conversation_id:
        raise ApplicationError(
            code="CONVERSATION_ID_MISMATCH",
            message="X-Conversation-ID must match body conversation_id",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    try:
        return service.create_call_outcome(request, session)
    except service.InvalidCallOutcomeReferenceError as error:
        raise ApplicationError(
            code=error.code,
            message=str(error),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from error
