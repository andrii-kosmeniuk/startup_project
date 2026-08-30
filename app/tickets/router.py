from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.tickets import service
from app.tickets.schemas import Ticket, TicketCreate
from app.data.database import get_db
from app.security.api_key import require_api_key
from app.errors import ApplicationError
from app.idempotency.dependencies import require_event_id

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
def create_ticket(
    request: TicketCreate,
    response: Response,
    session: Session = Depends(get_db),
    event_id: str = Depends(require_event_id),
) -> Ticket:
    try:
        result = service.create_ticket(request, event_id, session)
        response.status_code = result.response_status
        if result.replayed:
            response.headers["X-Idempotent-Replay"] = "true"
        if result.response_status == status.HTTP_200_OK:
            response.headers["X-Existing-Ticket"] = "true"
        response.headers["X-Event-ID"] = event_id
        return result.ticket
    except service.InvalidTicketReferenceError as error:
        raise ApplicationError(
            code=error.code,
            message=str(error),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from error
