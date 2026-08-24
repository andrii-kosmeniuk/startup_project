import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.models import ProcessedEventRecord
from app.errors import ApplicationError
from app.observability.logging import log_event

EVENT_STATUS_PROCESSING = "processing"
EVENT_STATUS_COMPLETED = "completed"


def request_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def claim_or_replay(
    *,
    event_id: str,
    operation: str,
    payload: dict[str, Any],
    session: Session,
) -> ProcessedEventRecord | None:
    payload_hash = request_hash(payload)
    existing = session.get(ProcessedEventRecord, event_id)
    if existing is not None:
        return _validated_replay(existing, operation, payload_hash)

    record = ProcessedEventRecord(
        event_id=event_id,
        operation=operation,
        request_hash=payload_hash,
        status=EVENT_STATUS_PROCESSING,
        response_status=None,
        response_body=None,
        result_reference=None,
        processed_at=datetime.now(timezone.utc),
    )
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = session.get(ProcessedEventRecord, event_id)
        if existing is None:
            raise
        return _validated_replay(existing, operation, payload_hash)
    return None


def complete_event(
    *,
    event_id: str,
    response_status: int,
    response_body: dict[str, Any],
    result_reference: str,
    session: Session,
) -> None:
    record = session.get(ProcessedEventRecord, event_id)
    if record is None:
        raise RuntimeError("Claimed processed event is missing")
    record.status = EVENT_STATUS_COMPLETED
    record.response_status = response_status
    record.response_body = response_body
    record.result_reference = result_reference
    record.processed_at = datetime.now(timezone.utc)


def _validated_replay(
    record: ProcessedEventRecord, operation: str, payload_hash: str
) -> ProcessedEventRecord:
    if record.operation != operation or record.request_hash != payload_hash:
        raise ApplicationError(
            code="IDEMPOTENCY_KEY_REUSED",
            message="X-Event-ID was already used for a different request",
            status_code=status.HTTP_409_CONFLICT,
        )
    if record.status != EVENT_STATUS_COMPLETED or record.response_body is None:
        raise ApplicationError(
            code="EVENT_PROCESSING",
            message="The event is still being processed",
            status_code=status.HTTP_409_CONFLICT,
            retryable=True,
        )
    log_event(
        "duplicate_event_replayed",
        event_id=record.event_id,
        operation=record.operation,
        result_reference=record.result_reference,
    )
    return record
