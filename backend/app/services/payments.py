import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Charge, Payment

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


async def _total_paid(session: AsyncSession, lease_id) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.lease_id == lease_id)
    )
    return Decimal(result.scalar_one())


async def _charges(session: AsyncSession, lease_id) -> list[Charge]:
    result = await session.execute(select(Charge).where(Charge.lease_id == lease_id))
    return list(result.scalars().all())


async def lease_statuses(session: AsyncSession, lease_id, today: date) -> list[ChargeStatus]:
    return allocate(await _charges(session, lease_id), await _total_paid(session, lease_id), today)


async def lease_balance(session: AsyncSession, lease_id, today: date) -> Balance:
    charges = await _charges(session, lease_id)
    total = await _total_paid(session, lease_id)
    return summarize(allocate(charges, total, today), total, today)


async def org_charge_statuses(
    session: AsyncSession, organization_id, today: date
) -> dict[uuid.UUID, list[ChargeStatus]]:
    """Allocate payments across charges for every lease in the organization.

    Two queries regardless of lease count. The per-lease helpers issue two each,
    so looping them over an organization costs 2N.
    """
    charges = (
        (await session.execute(select(Charge).where(Charge.organization_id == organization_id)))
        .scalars()
        .all()
    )
    paid_rows = await session.execute(
        select(Payment.lease_id, func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.organization_id == organization_id)
        .group_by(Payment.lease_id)
    )
    paid = {lease_id: Decimal(total) for lease_id, total in paid_rows.all()}

    by_lease: dict[uuid.UUID, list[Charge]] = {}
    for charge in charges:
        by_lease.setdefault(charge.lease_id, []).append(charge)
    return {
        lease_id: allocate(rows, paid.get(lease_id, Decimal("0")), today)
        for lease_id, rows in by_lease.items()
    }
