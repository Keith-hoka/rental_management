from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.models import Charge

ChargeState = Literal["unpaid", "partial", "paid"]


@dataclass
class ChargeStatus:
    charge: Charge
    amount_paid: Decimal
    status: ChargeState
    overdue: bool


@dataclass
class Balance:
    outstanding: Decimal
    overdue_amount: Decimal
    credit: Decimal


def allocate(charges: list[Charge], total_paid: Decimal, today: date) -> list[ChargeStatus]:
    """Waterfall-allocate total_paid across charges, oldest due date first."""
    pool = total_paid
    result: list[ChargeStatus] = []
    for charge in sorted(charges, key=lambda c: (c.due_date, c.period_start)):
        allocated = min(pool, charge.amount_due)
        pool -= allocated
        if allocated <= 0:
            status: ChargeState = "unpaid"
        elif allocated < charge.amount_due:
            status = "partial"
        else:
            status = "paid"
        overdue = charge.due_date < today and allocated < charge.amount_due
        result.append(ChargeStatus(charge, allocated, status, overdue))
    return result


def summarize(statuses: list[ChargeStatus], total_paid: Decimal, today: date) -> Balance:
    """Reduce per-charge allocation to outstanding / overdue / credit totals."""
    outstanding = Decimal("0")
    overdue_amount = Decimal("0")
    allocated_total = Decimal("0")
    for s in statuses:
        allocated_total += s.amount_paid
        remaining = s.charge.amount_due - s.amount_paid
        if s.charge.due_date <= today:
            outstanding += remaining
        if s.charge.due_date < today:
            overdue_amount += remaining
    return Balance(
        outstanding=outstanding,
        overdue_amount=overdue_amount,
        credit=total_paid - allocated_total,
    )
