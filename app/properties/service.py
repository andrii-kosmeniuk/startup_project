from sqlalchemy.orm import Session

from app.data.models import PropertyRecord
from app.properties.schemas import Property


def get_by_id(property_id: str, session: Session) -> Property | None:
    record = session.get(PropertyRecord, property_id)
    return Property.model_validate(record) if record is not None else None
