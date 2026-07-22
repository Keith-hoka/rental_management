import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import PaymentMethod


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date
    method: PaymentMethod
    note: str | None = None


class PaymentInfo(BaseModel):
    id: uuid.UUID
    amount: Decimal
    paid_on: date
    method: PaymentMethod
    note: str | None


class RecentPayment(BaseModel):
    id: uuid.UUID
    amount: Decimal
    paid_on: date
    method: PaymentMethod
    property_address: str
    tenant_name: str


class BalanceInfo(BaseModel):
    outstanding: Decimal
    overdue_amount: Decimal
    credit: Decimal
