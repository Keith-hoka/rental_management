import uuid

from pydantic import BaseModel


class MonthPoint(BaseModel):
    month: str
    income: float
    expenses: float
    net: float


class CategoryTotal(BaseModel):
    category: str
    total: float


class PropertyPnl(BaseModel):
    property_id: uuid.UUID | None
    address: str
    income: float
    expenses: float
    net: float


class MonthlyReport(BaseModel):
    months: list[MonthPoint]
    by_category: list[CategoryTotal]
    by_property: list[PropertyPnl]
