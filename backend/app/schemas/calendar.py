import uuid
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CalendarEventCreate(BaseModel):
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    property_id: uuid.UUID | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    property_id: uuid.UUID | None = None


class CalendarEventInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    property_id: uuid.UUID | None
    created_at: datetime


class CalendarEntry(BaseModel):
    kind: str
    title: str
    all_day: bool
    date: date_type | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    link: str | None = None
    event_id: uuid.UUID | None = None
