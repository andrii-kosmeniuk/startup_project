from sqlalchemy.orm import Session

from app.data.models import EmergencyContactRecord, PropertyManagerRecord, PropertyRecord
from app.properties.schemas import EmergencyContact, Property, PropertyManager


def get_by_id(property_id: str, session: Session) -> Property | None:
    record = session.get(PropertyRecord, property_id)
    return Property.model_validate(record) if record is not None else None


def get_manager(property_id: str, session: Session) -> PropertyManager | None:
    property_record = session.get(PropertyRecord, property_id)
    if property_record is None:
        return None
    record = session.get(PropertyManagerRecord, property_record.property_manager_id)
    return PropertyManager.model_validate(record) if record is not None else None


def get_emergency_contact(
    property_id: str, session: Session
) -> EmergencyContact | None:
    property_record = session.get(PropertyRecord, property_id)
    if property_record is None:
        return None
    record = session.get(EmergencyContactRecord, property_record.emergency_contact_id)
    return EmergencyContact.model_validate(record) if record is not None else None
