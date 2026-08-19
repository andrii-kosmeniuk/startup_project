from app.customers.schemas import Customer, CustomerLookupResponse, MatchStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models import CustomerRecord, TicketRecord
from app.tickets.schemas import Ticket, TicketStatus


def find_by_phone(phone: str, session: Session) -> CustomerLookupResponse:
    records = session.scalars(
        select(CustomerRecord).where(CustomerRecord.phone == phone)
    ).all()
    matches = [Customer.model_validate(record) for record in records]
    if not matches:
        status = MatchStatus.NOT_FOUND
    elif len(matches) == 1:
        status = MatchStatus.UNIQUE
    else:
        status = MatchStatus.AMBIGUOUS

    return CustomerLookupResponse(status=status, count=len(matches), customers=matches)


def customer_exists(customer_id: str, session: Session) -> bool:
    return session.get(CustomerRecord, customer_id) is not None


def get_open_tickets(customer_id: str, session: Session) -> list[Ticket]:
    records = session.scalars(
        select(TicketRecord).where(
            TicketRecord.customer_id == customer_id,
            TicketRecord.status != TicketStatus.CLOSED.value,
        )
    ).all()
    return [Ticket.model_validate(record) for record in records]
