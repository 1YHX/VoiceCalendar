from datetime import datetime

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ParsedCommand(BaseModel):
    intent: str
    title: str = ""
    description: str = ""
    start_time: str = ""
    end_time: str = ""
    reminder_minutes: int = 10
    confidence: float = 0.0
    clarification_question: str = ""


class EventCreate(BaseModel):
    title: str
    description: str = ""
    start_time: datetime
    end_time: datetime
    reminder_minutes: int = 10
    raw_text: str


class EventResponse(BaseModel):
    id: int
    title: str
    description: str = ""
    start_time: datetime
    end_time: datetime
    reminder_minutes: int
    raw_text: str

    class Config:
        from_attributes = True


class CommandResponse(BaseModel):
    success: bool
    message: str
    parsed: ParsedCommand | None = None
    event: EventResponse | None = None
    events: list[EventResponse] = Field(default_factory=list)


class AsrResponse(BaseModel):
    success: bool
    text: str
    mock: bool
