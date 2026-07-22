import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import MaintenancePriority, MaintenanceStatus


class MaintenanceCreate(BaseModel):
    title: str
    description: str
    priority: MaintenancePriority = MaintenancePriority.medium


class MaintenanceUpdate(BaseModel):
    status: MaintenanceStatus | None = None
    priority: MaintenancePriority | None = None


class MaintenanceInfo(BaseModel):
    id: uuid.UUID
    property_address: str
    title: str
    description: str
    priority: MaintenancePriority
    status: MaintenanceStatus
    image_urls: list[str]
    reported_by: str
    created_at: datetime
