from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CallOutcomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(min_length=1, max_length=100)
    customer_id: str | None = Field(default=None, min_length=1, max_length=100)
    intent: str = Field(min_length=1, max_length=100)
    ticket_id: str | None = Field(default=None, min_length=1, max_length=100)
    transfer_attempted: bool = Field(default=False, strict=True)
    transfer_success: bool = Field(default=False, strict=True)
    follow_up_required: bool = Field(default=False, strict=True)
    summary: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.transfer_success and not self.transfer_attempted:
            raise ValueError("A successful transfer must have been attempted")
        return self


class CallOutcome(CallOutcomeCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    created_at: datetime
