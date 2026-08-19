from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class TicketCreate(BaseModel):
    customer_id: str
    property_id: str
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    priority: TicketPriority


class Ticket(TicketCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: TicketStatus
