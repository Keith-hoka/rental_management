import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models import InspectionCondition, InspectionStatus, InspectionType


class InspectionItemIn(BaseModel):
    area: str
    condition: InspectionCondition
    note: str | None = None


class InspectionItemInfo(BaseModel):
    id: uuid.UUID
    area: str
    condition: InspectionCondition
    note: str | None


class InspectionCreate(BaseModel):
    property_id: uuid.UUID
    lease_id: uuid.UUID | None = None
    type: InspectionType
    status: InspectionStatus = InspectionStatus.scheduled
    scheduled_for: date
    note: str | None = None
    items: list[InspectionItemIn] = []


class InspectionUpdate(BaseModel):
    status: InspectionStatus | None = None
    note: str | None = None
    scheduled_for: date | None = None
    items: list[InspectionItemIn] | None = None


class InspectionInfo(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    lease_id: uuid.UUID | None
    type: InspectionType
    status: InspectionStatus
    scheduled_for: date
    note: str | None
    image_urls: list[str]
    items: list[InspectionItemInfo]
    created_at: datetime
