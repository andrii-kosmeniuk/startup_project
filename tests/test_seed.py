from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.data.database import Base
from app.data.models import (
    CallOutcomeRecord,
    CustomerRecord,
    EmergencyContactRecord,
    ProcessedEventRecord,
    PropertyManagerRecord,
    PropertyRecord,
    TicketRecord,
)
from app.data.seed import reset_demo_data, seed_database


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    with Session(engine, expire_on_commit=False) as database_session:
        yield database_session
    Base.metadata.drop_all(bind=engine)


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_database_creates_exact_canonical_dataset(session: Session) -> None:
    seed_database(session)

    assert count(session, PropertyManagerRecord) == 2
    assert count(session, EmergencyContactRecord) == 2
    assert count(session, PropertyRecord) == 2
    assert count(session, CustomerRecord) == 4
    assert count(session, TicketRecord) == 1
    assert count(session, CallOutcomeRecord) == 0
    assert count(session, ProcessedEventRecord) == 0

    anna = session.get(CustomerRecord, "customer-anna-mueller")
    assert anna is not None
    assert (anna.first_name, anna.last_name, anna.phone) == (
        "Anna",
        "Müller",
        "+436601234567",
    )

    ambiguous_callers = session.scalars(
        select(CustomerRecord)
        .where(CustomerRecord.phone == "+436609999999")
        .order_by(CustomerRecord.id)
    ).all()
    assert [(caller.first_name, caller.last_name) for caller in ambiguous_callers] == [
        ("Laura", "Berger"),
        ("Michael", "Berger"),
    ]

    assert session.get(PropertyManagerRecord, "manager-1").available is True
    assert session.get(PropertyManagerRecord, "manager-2").available is False
    assert session.get(EmergencyContactRecord, "emergency-1").available is True
    assert session.get(EmergencyContactRecord, "emergency-2").available is False

    ticket = session.get(TicketRecord, "ticket-932")
    assert ticket is not None
    assert ticket.customer_id == "customer-anna-mueller"
    assert ticket.property_id == "property-neubaugasse-17"
    assert ticket.category == "heating"
    assert ticket.priority == "medium"
    assert ticket.status == "in_progress"
    assert count(
        session,
        TicketRecord,
    ) == 1
    assert session.scalar(
        select(func.count())
        .select_from(TicketRecord)
        .where(TicketRecord.category == "string")
    ) == 0


def test_seed_is_idempotent_and_does_not_overwrite_existing_data(
    session: Session,
) -> None:
    seed_database(session)
    anna = session.get(CustomerRecord, "customer-anna-mueller")
    anna.first_name = "Locally customized"
    session.commit()

    seed_database(session)

    assert session.get(CustomerRecord, "customer-anna-mueller").first_name == (
        "Locally customized"
    )
    assert count(session, CustomerRecord) == 4
    assert count(session, TicketRecord) == 1


def test_seed_recovers_a_partially_missing_dataset(session: Session) -> None:
    seed_database(session)
    session.delete(session.get(CustomerRecord, "customer-lukas-huber"))
    session.commit()

    seed_database(session)

    assert session.get(CustomerRecord, "customer-lukas-huber") is not None
    assert count(session, CustomerRecord) == 4


def test_reset_removes_junk_and_restores_only_canonical_data(
    session: Session,
) -> None:
    seed_database(session)
    session.add(
        TicketRecord(
            id="ticket-swagger-junk",
            customer_id="customer-anna-mueller",
            property_id="property-neubaugasse-17",
            category="string",
            description="string",
            priority="low",
            status="open",
        )
    )
    session.add(
        CallOutcomeRecord(
            id="outcome-test-junk",
            conversation_id="conversation-test-junk",
            customer_id="customer-anna-mueller",
            intent="test",
            ticket_id="ticket-swagger-junk",
            transfer_attempted=False,
            transfer_success=False,
            follow_up_required=False,
            summary="Temporary test outcome",
            created_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        ProcessedEventRecord(
            event_id="event-test-junk",
            operation="test",
            request_hash="a" * 64,
            status="completed",
            response_status=200,
            response_body={"temporary": True},
            result_reference="outcome-test-junk",
            processed_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    reset_demo_data(session)

    assert count(session, PropertyManagerRecord) == 2
    assert count(session, EmergencyContactRecord) == 2
    assert count(session, PropertyRecord) == 2
    assert count(session, CustomerRecord) == 4
    assert count(session, TicketRecord) == 1
    assert count(session, CallOutcomeRecord) == 0
    assert count(session, ProcessedEventRecord) == 0
    assert session.get(TicketRecord, "ticket-932") is not None
    assert session.get(TicketRecord, "ticket-swagger-junk") is None


def test_reset_rolls_back_deletions_when_reseed_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_database(session)
    session.add(
        TicketRecord(
            id="ticket-must-survive-rollback",
            customer_id="customer-anna-mueller",
            property_id="property-neubaugasse-17",
            category="plumbing",
            description="Existing data",
            priority="low",
            status="open",
        )
    )
    session.commit()

    def fail_seed(_session: Session, *, commit: bool = True) -> None:
        raise RuntimeError("simulated reseed failure")

    monkeypatch.setattr("app.data.seed.seed_database", fail_seed)

    with pytest.raises(RuntimeError, match="simulated reseed failure"):
        reset_demo_data(session)

    assert session.get(TicketRecord, "ticket-must-survive-rollback") is not None
    assert session.get(TicketRecord, "ticket-932") is not None


def test_reset_cli_requires_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.data import reset_demo

    monkeypatch.delenv(reset_demo.CONFIRMATION_VARIABLE, raising=False)

    with pytest.raises(SystemExit, match="Refusing to reset data"):
        reset_demo.main()
