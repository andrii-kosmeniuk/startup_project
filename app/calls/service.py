from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.calls.schemas import CallOutcome, CallOutcomeCreate
from app.data.models import CallOutcomeRecord, CustomerRecord, TicketRecord


class InvalidCallOutcomeReferenceError(ValueError):
    pass


def create_call_outcome(request: CallOutcomeCreate, session: Session) -> CallOutcome:
    if request.customer_id and session.get(CustomerRecord, request.customer_id) is None:
        raise InvalidCallOutcomeReferenceError("Customer not found")
    if request.ticket_id and session.get(TicketRecord, request.ticket_id) is None:
        raise InvalidCallOutcomeReferenceError("Ticket not found")

    record = CallOutcomeRecord(
        id=f"call-outcome-{uuid4().hex}",
        created_at=datetime.now(timezone.utc),
        **request.model_dump(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return CallOutcome.model_validate(record)
