from app.customers.schemas import Customer, CustomerLookupResponse, MatchStatus
from app.data.mock_data import CUSTOMERS, TICKETS
from app.tickets.schemas import Ticket, TicketStatus


def find_by_phone(phone: str) -> CustomerLookupResponse:
    matches = [customer for customer in CUSTOMERS if customer.phone == phone]
    if not matches:
        status = MatchStatus.NOT_FOUND
    elif len(matches) == 1:
        status = MatchStatus.UNIQUE
    else:
        status = MatchStatus.AMBIGUOUS

    return CustomerLookupResponse(status=status, count=len(matches), customers=matches)


def customer_exists(customer_id: str) -> bool:
    return any(customer.id == customer_id for customer in CUSTOMERS)


def get_open_tickets(customer_id: str) -> list[Ticket]:
    return [
        ticket
        for ticket in TICKETS
        if ticket.customer_id == customer_id and ticket.status != TicketStatus.CLOSED
    ]
