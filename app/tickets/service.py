from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.data.models import CustomerRecord, PropertyRecord, TicketRecord
from app.tickets.schemas import Ticket, TicketCreate, TicketPriority, TicketStatus
from app.observability.logging import log_event
from app.idempotency import service as idempotency


class InvalidTicketReferenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TicketOperationResult:
    ticket: Ticket
    replayed: bool
    response_status: int


_PRIORITY_RANK = {
    TicketPriority.LOW.value: 0,
    TicketPriority.MEDIUM.value: 1,
    TicketPriority.HIGH.value: 2,
    TicketPriority.CRITICAL.value: 3,
}


def _lock_ticket_issue(request: TicketCreate, session: Session) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        issue_key = f"{request.customer_id}:{request.property_id}:{request.category}"
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:issue_key, 0))"),
            {"issue_key": issue_key},
        )


def _find_matching_open_ticket(
    request: TicketCreate, session: Session
) -> TicketRecord | None:
    return session.scalar(
        select(TicketRecord)
        .where(
            TicketRecord.customer_id == request.customer_id,
            TicketRecord.property_id == request.property_id,
            TicketRecord.category == request.category,
            TicketRecord.status != TicketStatus.CLOSED.value,
        )
        .order_by(TicketRecord.id)
        .limit(1)
    )


def create_ticket(
    request: TicketCreate, event_id: str, session: Session
) -> TicketOperationResult:
    payload = request.model_dump(mode="json")
    try:
        replay = idempotency.claim_or_replay(
            event_id=event_id,
            operation="create_ticket",
            payload=payload,
            session=session,
        )
        if replay is not None:
            return TicketOperationResult(
                ticket=Ticket.model_validate(replay.response_body),
                replayed=True,
                response_status=replay.response_status or 201,
            )

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

        _lock_ticket_issue(request, session)
        existing = _find_matching_open_ticket(request, session)
        if existing is not None:
            if _PRIORITY_RANK[request.priority.value] > _PRIORITY_RANK[existing.priority]:
                existing.priority = request.priority.value
                log_event(
                    "existing_ticket_priority_escalated",
                    ticket_id=existing.id,
                )
            ticket = Ticket.model_validate(existing)
            idempotency.complete_event(
                event_id=event_id,
                response_status=200,
                response_body=ticket.model_dump(mode="json"),
                result_reference=existing.id,
                session=session,
            )
            session.commit()
            log_event("existing_ticket_found", ticket_id=existing.id)
            return TicketOperationResult(ticket, False, 200)

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
        return TicketOperationResult(ticket, False, 201)
    except Exception:
        session.rollback()
        raise
