import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PropertyType(str, enum.Enum):
    apartment = "apartment"
    house = "house"
    condo = "condo"
    townhouse = "townhouse"
    other = "other"


class PropertyStatus(str, enum.Enum):
    vacant = "vacant"
    occupied = "occupied"


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    address: Mapped[str] = mapped_column(String(500))
    state: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(20))
    type: Mapped[PropertyType] = mapped_column(Enum(PropertyType))
    bedrooms: Mapped[int] = mapped_column(default=0)
    bathrooms: Mapped[int] = mapped_column(default=0)
    parking: Mapped[int] = mapped_column(default=0)
    description: Mapped[str | None] = mapped_column(String(2000))
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
