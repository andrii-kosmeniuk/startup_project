from uuid import uuid4

from app.data.mock_data import CUSTOMERS, PROPERTIES, TICKETS
from app.tickets.schemas import Ticket, TicketCreate, TicketStatus


class InvalidTicketReferenceError(ValueError):
    pass


def create_ticket(request: TicketCreate) -> Ticket:
    customer = next(
        (item for item in CUSTOMERS if item.id == request.customer_id), None
    )
    if customer is None:
        raise InvalidTicketReferenceError("Customer not found")
    if not any(item.id == request.property_id for item in PROPERTIES):
        raise InvalidTicketReferenceError("Property not found")
    if customer.property_id != request.property_id:
        raise InvalidTicketReferenceError("Customer does not belong to this property")

    ticket = Ticket(
        id=f"ticket-{uuid4().hex}",
        status=TicketStatus.OPEN,
        **request.model_dump(),
    )
    TICKETS.append(ticket)
    return ticket
