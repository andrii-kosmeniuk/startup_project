from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.calls.schemas import CallOutcome, CallOutcomeCreate
from app.data.models import CallOutcomeRecord, CustomerRecord, TicketRecord
from app.observability.logging import log_event


class InvalidCallOutcomeReferenceError(ValueError):
    pass


def create_call_outcome(request: CallOutcomeCreate, session: Session) -> CallOutcome:
    if request.customer_id and session.get(CustomerRecord, request.customer_id) is None:
        raise InvalidCallOutcomeReferenceError("Customer not found")
    if request.ticket_id:
        ticket = session.get(TicketRecord, request.ticket_id)
        if ticket is None:
            raise InvalidCallOutcomeReferenceError("Ticket not found")
        if request.customer_id and ticket.customer_id != request.customer_id:
            raise InvalidCallOutcomeReferenceError(
                "Ticket does not belong to this customer"
            )

    record = CallOutcomeRecord(
        id=f"call-outcome-{uuid4().hex}",
        created_at=datetime.now(timezone.utc),
        **request.model_dump(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    log_event(
        "call_outcome_saved",
        call_outcome_id=record.id,
        intent=record.intent,
        follow_up_required=record.follow_up_required,
    )
    return CallOutcome.model_validate(record)
