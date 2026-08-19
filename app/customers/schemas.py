from enum import Enum

from pydantic import BaseModel, ConfigDict


class Customer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    phone: str
    property_id: str
    unit: str
    property_manager_id: str


class MatchStatus(str, Enum):
    NOT_FOUND = "not_found"
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"


class CustomerLookupResponse(BaseModel):
    status: MatchStatus
    count: int
    customers: list[Customer]
