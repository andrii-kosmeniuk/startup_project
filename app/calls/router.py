from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.calls import service
from app.calls.schemas import CallOutcome, CallOutcomeCreate
from app.data.database import get_db
from app.security.api_key import require_api_key

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-Conversation-ID must match body conversation_id",
        )
    try:
        return service.create_call_outcome(request, session)
    except service.InvalidCallOutcomeReferenceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
