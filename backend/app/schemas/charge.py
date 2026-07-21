import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ChargeInfo(BaseModel):
    id: uuid.UUID
    period_start: date
    period_end: date
    due_date: date
    amount_due: Decimal
    amount_paid: Decimal
    status: Literal["unpaid", "partial", "paid"]
    overdue: bool
