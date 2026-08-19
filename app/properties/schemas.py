from pydantic import BaseModel


class Property(BaseModel):
    id: str
    address: str
    property_manager_id: str
    emergency_contact_id: str
