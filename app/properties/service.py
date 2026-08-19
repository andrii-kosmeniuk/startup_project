from app.data.mock_data import PROPERTIES
from app.properties.schemas import Property


def get_by_id(property_id: str) -> Property | None:
    return next((item for item in PROPERTIES if item.id == property_id), None)
