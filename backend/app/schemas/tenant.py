import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.models.lease import LeaseFrequency


class TenantInviteRequest(BaseModel):
    email: EmailStr


class LeaseTenantInfo(BaseModel):
    name: str
    email: EmailStr


class LeaseInvitationInfo(BaseModel):
    id: uuid.UUID
    email: EmailStr


class TenantLease(BaseModel):
    id: uuid.UUID
    property_address: str
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    start_date: date
    end_date: date
    bond_amount: Decimal | None
    notice_period_days: int | None
    state: Literal["active", "upcoming", "ended"]
    landlord_name: str
    landlord_email: EmailStr
    landlord_phone: str | None


class LeaseReminderInfo(BaseModel):
    threshold_days: int
    sent_at: datetime
