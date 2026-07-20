import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseFrequency(str, enum.Enum):
    weekly = "weekly"
    fortnightly = "fortnightly"
    monthly = "monthly"


class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    tenant_name: Mapped[str] = mapped_column(String(255))
    tenant_email: Mapped[str] = mapped_column(String(255))
    rent_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rent_frequency: Mapped[LeaseFrequency] = mapped_column(Enum(LeaseFrequency))
    bond_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notice_period_days: Mapped[int | None] = mapped_column()
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
