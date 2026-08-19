from enum import Enum

from pydantic import BaseModel


class Customer(BaseModel):
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
