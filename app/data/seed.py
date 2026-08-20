from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models import (
    CustomerRecord,
    EmergencyContactRecord,
    PropertyManagerRecord,
    PropertyRecord,
    TicketRecord,
)


def seed_database(session: Session) -> None:
    reference_records = [
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
            phone="+4315550202", type="building_emergency", available=True,
        ),
    ]
    for record in reference_records:
        if session.get(type(record), record.id) is None:
            session.add(record)

    if session.scalar(select(PropertyRecord.id).limit(1)) is not None:
        session.commit()
        return

    session.add_all(
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
        ]
    )
    session.flush()
    session.add_all(
        [
            CustomerRecord(
                id="customer-anna-mueller",
                first_name="Anna",
                last_name="Müller",
                phone="+436601234567",
                property_id="property-neubaugasse-17",
                unit="4B",
                property_manager_id="manager-1",
            ),
            CustomerRecord(
                id="customer-lukas-huber",
                first_name="Lukas",
                last_name="Huber",
                phone="+436609876543",
                property_id="property-landstrasser-42",
                unit="12A",
                property_manager_id="manager-2",
            ),
            CustomerRecord(
                id="customer-maria-schmidt",
                first_name="Maria",
                last_name="Schmidt",
                phone="+436601111111",
                property_id="property-neubaugasse-17",
                unit="2A",
                property_manager_id="manager-1",
            ),
            CustomerRecord(
                id="customer-paul-schmidt",
                first_name="Paul",
                last_name="Schmidt",
                phone="+436601111111",
                property_id="property-neubaugasse-17",
                unit="2A",
                property_manager_id="manager-1",
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            TicketRecord(
                id="ticket-1",
                customer_id="customer-lukas-huber",
                property_id="property-landstrasser-42",
                category="plumbing",
                description="Kitchen sink is leaking.",
                priority="medium",
                status="open",
            ),
            TicketRecord(
                id="ticket-2",
                customer_id="customer-lukas-huber",
                property_id="property-landstrasser-42",
                category="heating",
                description="Radiator valve was replaced.",
                priority="low",
                status="closed",
            ),
        ]
    )
    session.commit()
