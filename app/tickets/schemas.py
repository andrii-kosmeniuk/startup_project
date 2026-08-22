from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(min_length=1, max_length=100)
    property_id: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    priority: TicketPriority


class Ticket(TicketCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    status: TicketStatus
