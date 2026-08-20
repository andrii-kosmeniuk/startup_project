from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.calls import service
from app.calls.schemas import CallOutcome, CallOutcomeCreate
from app.data.database import get_db

router = APIRouter(prefix="/call-outcomes", tags=["call outcomes"])


@router.post("", response_model=CallOutcome, status_code=status.HTTP_201_CREATED)
def create_call_outcome(
    request: CallOutcomeCreate, session: Session = Depends(get_db)
) -> CallOutcome:
    try:
        return service.create_call_outcome(request, session)
    except service.InvalidCallOutcomeReferenceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
