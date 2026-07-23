import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ExpenseCategory(str, enum.Enum):
    maintenance = "maintenance"
    insurance = "insurance"
    tax = "tax"
    utilities = "utilities"
    management = "management"
    other = "other"


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    spent_on: Mapped[date] = mapped_column(Date)
    category: Mapped[ExpenseCategory] = mapped_column(Enum(ExpenseCategory))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
