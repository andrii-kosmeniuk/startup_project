from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.tickets import service
from app.tickets.schemas import Ticket, TicketCreate
from app.data.database import get_db

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
def create_ticket(
    request: TicketCreate, session: Session = Depends(get_db)
) -> Ticket:
    try:
        return service.create_ticket(request, session)
    except service.InvalidTicketReferenceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
