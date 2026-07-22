from decimal import Decimal

from pydantic import BaseModel


class MonthlyIncome(BaseModel):
    month: str
    # A float, not Decimal: Pydantic renders Decimal as a JSON string and the
    # chart cannot plot strings. The money totals above stay Decimal - they are
    # only ever displayed as text.
    amount: float


class DashboardStats(BaseModel):
    outstanding: Decimal
    overdue: Decimal
    collected_this_month: Decimal
    properties_total: int
    properties_occupied: int
    active_leases: int
    tenants: int
    monthly_income: list[MonthlyIncome]
