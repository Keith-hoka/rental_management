import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.lease import LeaseFrequency
from app.models.property import PropertyStatus, PropertyType


class PropertyCreate(BaseModel):
    address: str
    type: PropertyType
    bedrooms: int = 0
    bathrooms: int = 0
    parking: int = 0
    description: str | None = None
    image_urls: list[str] = []


class PropertyUpdate(BaseModel):
    address: str | None = None
    type: PropertyType | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    description: str | None = None
    image_urls: list[str] | None = None


class ActiveLease(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_name: str
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    start_date: date
    end_date: date


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    address: str
    type: PropertyType
    bedrooms: int
    bathrooms: int
    parking: int
    description: str | None
    status: PropertyStatus
    image_urls: list[str]
    active_lease: ActiveLease | None = None
