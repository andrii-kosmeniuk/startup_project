from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CallOutcomeCreate(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=100)
    customer_id: str | None = None
    intent: str = Field(min_length=1, max_length=100)
    ticket_id: str | None = None
    transfer_attempted: bool = False
    transfer_success: bool = False
    follow_up_required: bool = False
    summary: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.transfer_success and not self.transfer_attempted:
            raise ValueError("A successful transfer must have been attempted")
        return self


class CallOutcome(CallOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
