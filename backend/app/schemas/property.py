import uuid

from pydantic import BaseModel, ConfigDict

from app.models.property import PropertyStatus, PropertyType


class PropertyCreate(BaseModel):
    address: str
    type: PropertyType
    bedrooms: int = 0
    bathrooms: int = 0
    parking: int = 0
    description: str | None = None
    status: PropertyStatus = PropertyStatus.vacant
    image_urls: list[str] = []


class PropertyUpdate(BaseModel):
    address: str | None = None
    type: PropertyType | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    description: str | None = None
    status: PropertyStatus | None = None
    image_urls: list[str] | None = None


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
