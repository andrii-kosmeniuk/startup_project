from uuid import uuid4

from sqlalchemy.orm import Session

from app.data.models import CustomerRecord, PropertyRecord, TicketRecord
from app.tickets.schemas import Ticket, TicketCreate, TicketStatus


class InvalidTicketReferenceError(ValueError):
    pass


def create_ticket(request: TicketCreate, session: Session) -> Ticket:
    customer = session.get(CustomerRecord, request.customer_id)
    if customer is None:
        raise InvalidTicketReferenceError("Customer not found")
    if session.get(PropertyRecord, request.property_id) is None:
        raise InvalidTicketReferenceError("Property not found")
    if customer.property_id != request.property_id:
        raise InvalidTicketReferenceError("Customer does not belong to this property")

    record = TicketRecord(
        id=f"ticket-{uuid4().hex}",
        status=TicketStatus.OPEN.value,
        **request.model_dump(mode="json"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return Ticket.model_validate(record)
