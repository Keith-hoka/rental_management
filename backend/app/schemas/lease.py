import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.lease import LeaseFrequency


class CoTenant(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None


class LeaseCreate(BaseModel):
    tenant_name: str
    tenant_email: EmailStr
    tenant_phone: str | None = None
    co_tenants: list[CoTenant] = []
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    bond_amount: Decimal | None = None
    notice_period_days: int | None = None
    start_date: date
    end_date: date


class LeaseUpdate(BaseModel):
    tenant_name: str | None = None
    tenant_email: EmailStr | None = None
    tenant_phone: str | None = None
    co_tenants: list[CoTenant] | None = None
    rent_amount: Decimal | None = None
    rent_frequency: LeaseFrequency | None = None
    bond_amount: Decimal | None = None
    notice_period_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class LeaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    tenant_name: str
    tenant_email: EmailStr
    tenant_phone: str | None
    co_tenants: list[CoTenant]
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    bond_amount: Decimal | None
    notice_period_days: int | None
    start_date: date
    end_date: date
    created_at: datetime


class LeaseSummary(BaseModel):
    """A lease plus its property address and derived state, for the org-wide overview."""

    id: uuid.UUID
    property_id: uuid.UUID
    property_address: str
    tenant_name: str
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    start_date: date
    end_date: date
    state: Literal["active", "upcoming", "ended"]
