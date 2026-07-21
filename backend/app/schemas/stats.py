from decimal import Decimal

from pydantic import BaseModel


class MonthlyIncome(BaseModel):
    month: str
    amount: Decimal


class DashboardStats(BaseModel):
    outstanding: Decimal
    overdue: Decimal
    collected_this_month: Decimal
    properties_total: int
    properties_occupied: int
    active_leases: int
    tenants: int
    monthly_income: list[MonthlyIncome]
