from uuid import uuid4

from sqlalchemy.orm import Session

from app.data.models import CustomerRecord, PropertyRecord, TicketRecord
from app.tickets.schemas import Ticket, TicketCreate, TicketStatus
from app.observability.logging import log_event
from app.idempotency import service as idempotency


class InvalidTicketReferenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def create_ticket(
    request: TicketCreate, event_id: str, session: Session
) -> tuple[Ticket, bool]:
    payload = request.model_dump(mode="json")
    try:
        replay = idempotency.claim_or_replay(
            event_id=event_id,
            operation="create_ticket",
            payload=payload,
            session=session,
        )
        if replay is not None:
            return Ticket.model_validate(replay.response_body), True

        customer = session.get(CustomerRecord, request.customer_id)
        if customer is None:
            raise InvalidTicketReferenceError(
                "CUSTOMER_NOT_FOUND", "Customer not found"
            )
        if session.get(PropertyRecord, request.property_id) is None:
            raise InvalidTicketReferenceError(
                "PROPERTY_NOT_FOUND", "Property not found"
            )
        if customer.property_id != request.property_id:
            raise InvalidTicketReferenceError(
                "CUSTOMER_PROPERTY_MISMATCH",
                "Customer does not belong to this property",
            )

        record = TicketRecord(
            id=f"ticket-{uuid4().hex}",
            status=TicketStatus.OPEN.value,
            **payload,
        )
        session.add(record)
        session.flush()
        ticket = Ticket.model_validate(record)
        idempotency.complete_event(
            event_id=event_id,
            response_status=201,
            response_body=ticket.model_dump(mode="json"),
            result_reference=record.id,
            session=session,
        )
        session.commit()
        log_event("ticket_created", ticket_id=record.id, priority=record.priority)
        return ticket, False
    except Exception:
        session.rollback()
        raise
