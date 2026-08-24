from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.calls.schemas import CallOutcome, CallOutcomeCreate
from app.data.models import CallOutcomeRecord, CustomerRecord, TicketRecord
from app.observability.logging import log_event
from app.idempotency import service as idempotency


class InvalidCallOutcomeReferenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def create_call_outcome(
    request: CallOutcomeCreate, event_id: str, session: Session
) -> tuple[CallOutcome, bool]:
    payload = request.model_dump(mode="json")
    try:
        replay = idempotency.claim_or_replay(
            event_id=event_id,
            operation="create_call_outcome",
            payload=payload,
            session=session,
        )
        if replay is not None:
            return CallOutcome.model_validate(replay.response_body), True

        if (
            request.customer_id
            and session.get(CustomerRecord, request.customer_id) is None
        ):
            raise InvalidCallOutcomeReferenceError(
                "CUSTOMER_NOT_FOUND", "Customer not found"
            )
        if request.ticket_id:
            ticket = session.get(TicketRecord, request.ticket_id)
            if ticket is None:
                raise InvalidCallOutcomeReferenceError(
                    "TICKET_NOT_FOUND", "Ticket not found"
                )
            if request.customer_id and ticket.customer_id != request.customer_id:
                raise InvalidCallOutcomeReferenceError(
                    "TICKET_CUSTOMER_MISMATCH",
                    "Ticket does not belong to this customer",
                )

        record = CallOutcomeRecord(
            id=f"call-outcome-{uuid4().hex}",
            created_at=datetime.now(timezone.utc),
            **payload,
        )
        session.add(record)
        session.flush()
        outcome = CallOutcome.model_validate(record)
        idempotency.complete_event(
            event_id=event_id,
            response_status=201,
            response_body=outcome.model_dump(mode="json"),
            result_reference=record.id,
            session=session,
        )
        session.commit()
        log_event(
            "call_outcome_saved",
            call_outcome_id=record.id,
            intent=record.intent,
            follow_up_required=record.follow_up_required,
        )
        return outcome, False
    except Exception:
        session.rollback()
        raise
