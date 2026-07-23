import uuid
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Charge, Expense, Lease, Property
from app.schemas.report import CategoryTotal, MonthlyReport, MonthPoint, PropertyPnl


def _key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


async def monthly_report(session: AsyncSession, org: uuid.UUID, months: int) -> MonthlyReport:
    """A months-long accrual P&L: income from charges due, minus recorded expenses."""
    first_this = date.today().replace(day=1)
    start = first_this - relativedelta(months=months - 1)
    end = first_this + relativedelta(months=1) - relativedelta(days=1)
    keys = [_key(start + relativedelta(months=i)) for i in range(months)]

    income_m: dict[str, float] = defaultdict(float)
    for due, amt in (
        await session.execute(
            select(Charge.due_date, Charge.amount_due).where(
                Charge.organization_id == org,
                Charge.due_date >= start,
                Charge.due_date <= end,
            )
        )
    ).all():
        income_m[_key(due)] += float(amt)

    expense_m: dict[str, float] = defaultdict(float)
    cat: dict[str, float] = defaultdict(float)
    for spent, amt, category in (
        await session.execute(
            select(Expense.spent_on, Expense.amount, Expense.category).where(
                Expense.organization_id == org,
                Expense.spent_on >= start,
                Expense.spent_on <= end,
            )
        )
    ).all():
        expense_m[_key(spent)] += float(amt)
        cat[category.value] += float(amt)

    months_out = [
        MonthPoint(
            month=k,
            income=round(income_m[k], 2),
            expenses=round(expense_m[k], 2),
            net=round(income_m[k] - expense_m[k], 2),
        )
        for k in keys
    ]
    by_category = sorted(
        (CategoryTotal(category=c, total=round(t, 2)) for c, t in cat.items()),
        key=lambda x: x.total,
        reverse=True,
    )

    prop_income: dict[uuid.UUID, float] = defaultdict(float)
    for pid, total in (
        await session.execute(
            select(Lease.property_id, func.sum(Charge.amount_due))
            .join(Charge, Charge.lease_id == Lease.id)
            .where(
                Charge.organization_id == org,
                Charge.due_date >= start,
                Charge.due_date <= end,
            )
            .group_by(Lease.property_id)
        )
    ).all():
        prop_income[pid] += float(total)

    prop_expense: dict[uuid.UUID | None, float] = defaultdict(float)
    for pid, total in (
        await session.execute(
            select(Expense.property_id, func.sum(Expense.amount))
            .where(
                Expense.organization_id == org,
                Expense.spent_on >= start,
                Expense.spent_on <= end,
            )
            .group_by(Expense.property_id)
        )
    ).all():
        prop_expense[pid] += float(total)

    addresses = dict(
        (
            await session.execute(
                select(Property.id, Property.address).where(Property.organization_id == org)
            )
        ).all()
    )

    by_property: list[PropertyPnl] = []
    for pid in set(prop_income) | (set(prop_expense) - {None}):
        inc = round(prop_income.get(pid, 0.0), 2)
        exp = round(prop_expense.get(pid, 0.0), 2)
        by_property.append(
            PropertyPnl(
                property_id=pid,
                address=addresses.get(pid, ""),
                income=inc,
                expenses=exp,
                net=round(inc - exp, 2),
            )
        )
    if None in prop_expense:
        exp = round(prop_expense[None], 2)
        by_property.append(
            PropertyPnl(
                property_id=None,
                address="(Unassigned)",
                income=0.0,
                expenses=exp,
                net=round(-exp, 2),
            )
        )
    by_property.sort(key=lambda p: p.net)

    return MonthlyReport(months=months_out, by_category=by_category, by_property=by_property)
