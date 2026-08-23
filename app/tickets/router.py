from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.tickets import service
from app.tickets.schemas import Ticket, TicketCreate
from app.data.database import get_db
from app.security.api_key import require_api_key
from app.errors import ApplicationError

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
def create_ticket(
    request: TicketCreate, session: Session = Depends(get_db)
) -> Ticket:
    try:
        return service.create_ticket(request, session)
    except service.InvalidTicketReferenceError as error:
        raise ApplicationError(
            code=error.code,
            message=str(error),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from error
