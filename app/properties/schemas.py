from pydantic import BaseModel, ConfigDict


class Property(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    address: str
    property_manager_id: str
    emergency_contact_id: str
