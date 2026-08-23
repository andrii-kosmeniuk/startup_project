from uuid import uuid4

from sqlalchemy.orm import Session

from app.data.models import CustomerRecord, PropertyRecord, TicketRecord
from app.tickets.schemas import Ticket, TicketCreate, TicketStatus
from app.observability.logging import log_event


class InvalidTicketReferenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def create_ticket(request: TicketCreate, session: Session) -> Ticket:
    customer = session.get(CustomerRecord, request.customer_id)
    if customer is None:
        raise InvalidTicketReferenceError("CUSTOMER_NOT_FOUND", "Customer not found")
    if session.get(PropertyRecord, request.property_id) is None:
        raise InvalidTicketReferenceError("PROPERTY_NOT_FOUND", "Property not found")
    if customer.property_id != request.property_id:
        raise InvalidTicketReferenceError(
            "CUSTOMER_PROPERTY_MISMATCH",
            "Customer does not belong to this property",
        )

    record = TicketRecord(
        id=f"ticket-{uuid4().hex}",
        status=TicketStatus.OPEN.value,
        **request.model_dump(mode="json"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    log_event("ticket_created", ticket_id=record.id, priority=record.priority)
    return Ticket.model_validate(record)
