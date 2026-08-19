from fastapi import APIRouter, HTTPException, status

from app.tickets import service
from app.tickets.schemas import Ticket, TicketCreate

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
def create_ticket(request: TicketCreate) -> Ticket:
    try:
        return service.create_ticket(request)
    except service.InvalidTicketReferenceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
