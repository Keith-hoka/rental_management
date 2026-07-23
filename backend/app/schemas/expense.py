import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import ExpenseCategory


class ExpenseCreate(BaseModel):
    amount: Decimal
    spent_on: date
    category: ExpenseCategory
    note: str | None = None
    property_id: uuid.UUID | None = None


class ExpenseInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: Decimal
    spent_on: date
    category: ExpenseCategory
    note: str | None
    property_id: uuid.UUID | None
    created_at: datetime
