from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.data.models import (
    CallOutcomeRecord,
    CustomerRecord,
    EmergencyContactRecord,
    ProcessedEventRecord,
    PropertyManagerRecord,
    PropertyRecord,
    TicketRecord,
)


def _add_missing(session: Session, records: list[object]) -> None:
    for record in records:
        if session.get(type(record), record.id) is None:
            session.add(record)
    session.flush()


def seed_database(session: Session, *, commit: bool = True) -> None:
    """Insert missing canonical demo records without overwriting live data."""
    _add_missing(
        session,
        [
            PropertyManagerRecord(
                id="manager-1", first_name="Lukas", last_name="Berger",
                phone="+4315550101", email="lukas.berger@hauspilot.example",
                available=True,
            ),
            PropertyManagerRecord(
                id="manager-2", first_name="Sophie", last_name="Wagner",
                phone="+4315550102", email="sophie.wagner@hauspilot.example",
                available=False,
            ),
            EmergencyContactRecord(
                id="emergency-1", name="Wiener Notdienst",
                phone="+4315550201", type="building_emergency", available=True,
            ),
            EmergencyContactRecord(
                id="emergency-2", name="Haustechnik Bereitschaft",
                phone="+4315550202", type="building_emergency", available=False,
            ),
        ],
    )
    _add_missing(
        session,
        [
            PropertyRecord(
                id="property-neubaugasse-17",
                address="Neubaugasse 17, 1070 Wien",
                property_manager_id="manager-1",
                emergency_contact_id="emergency-1",
            ),
            PropertyRecord(
                id="property-landstrasser-42",
                address="Landstraßer Hauptstraße 42, 1030 Wien",
                property_manager_id="manager-2",
                emergency_contact_id="emergency-2",
            ),
        ],
    )
    _add_missing(
        session,
        [
            CustomerRecord(
                id="customer-anna-mueller", first_name="Anna", last_name="Müller",
                phone="+436601234567", property_id="property-neubaugasse-17",
                unit="4B", property_manager_id="manager-1",
            ),
            CustomerRecord(
                id="customer-lukas-huber", first_name="Lukas", last_name="Huber",
                phone="+436609876543", property_id="property-landstrasser-42",
                unit="12A", property_manager_id="manager-2",
            ),
            CustomerRecord(
                id="customer-laura-berger", first_name="Laura", last_name="Berger",
                phone="+436609999999", property_id="property-neubaugasse-17",
                unit="2A", property_manager_id="manager-1",
            ),
            CustomerRecord(
                id="customer-michael-berger", first_name="Michael",
                last_name="Berger", phone="+436609999999",
                property_id="property-neubaugasse-17", unit="2A",
                property_manager_id="manager-1",
            ),
        ],
    )
    _add_missing(
        session,
        [
            TicketRecord(
                id="ticket-932", customer_id="customer-anna-mueller",
                property_id="property-neubaugasse-17", category="heating",
                description="Heating is not working; technician visit scheduled.",
                priority="medium", status="in_progress",
            )
        ],
    )
    if commit:
        session.commit()
    else:
        session.flush()


def reset_demo_data(session: Session) -> None:
    """Delete application data and restore the canonical local demo dataset."""
    try:
        for model in (
            ProcessedEventRecord,
            CallOutcomeRecord,
            TicketRecord,
            CustomerRecord,
            PropertyRecord,
            EmergencyContactRecord,
            PropertyManagerRecord,
        ):
            session.execute(delete(model))
        seed_database(session, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
