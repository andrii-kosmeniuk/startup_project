from pydantic import BaseModel, ConfigDict


class Property(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    address: str
    property_manager_id: str
    emergency_contact_id: str


class PropertyManager(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    phone: str
    email: str
    available: bool


class EmergencyContact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    phone: str
    type: str
    available: bool
