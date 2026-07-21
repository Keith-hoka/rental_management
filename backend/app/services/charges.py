from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Charge, Lease, LeaseFrequency


def _period_start(start_date: date, frequency: LeaseFrequency, n: int) -> date:
    """The nth period's start date, anchored to start_date and stepped by frequency."""
    if frequency == LeaseFrequency.weekly:
        return start_date + timedelta(weeks=n)
    if frequency == LeaseFrequency.fortnightly:
        return start_date + timedelta(weeks=2 * n)
    return start_date + relativedelta(months=n)


def _period_starts(lease: Lease, horizon: date) -> list[date]:
    """Every period start from the lease start up to min(horizon, lease.end_date)."""
    limit = min(horizon, lease.end_date)
    starts: list[date] = []
    n = 0
    while True:
        ps = _period_start(lease.start_date, lease.rent_frequency, n)
        if ps > limit:
            break
        starts.append(ps)
        n += 1
    return starts


async def _existing_period_starts(session: AsyncSession, lease_id) -> set[date]:
    result = await session.execute(select(Charge.period_start).where(Charge.lease_id == lease_id))
    return {ps for (ps,) in result.all()}


async def generate_charges(session: AsyncSession, today: date) -> int:
    """Generate rent charges for every lease period due within the lead window.

    Returns the number of charges created this run.
    """
    horizon = today + timedelta(days=settings.charge_lead_days)
    leases = (
        (await session.execute(select(Lease).where(Lease.start_date <= horizon))).scalars().all()
    )
    created = 0
    for lease in leases:
        starts = _period_starts(lease, horizon)
        if not starts:
            continue
        existing = await _existing_period_starts(session, lease.id)
        new_count = 0
        for i, ps in enumerate(starts):
            if ps in existing:
                continue
            next_start = _period_start(lease.start_date, lease.rent_frequency, i + 1)
            period_end = min(next_start - timedelta(days=1), lease.end_date)
            session.add(
                Charge(
                    organization_id=lease.organization_id,
                    lease_id=lease.id,
                    period_start=ps,
                    period_end=period_end,
                    due_date=ps,
                    amount_due=lease.rent_amount,
                )
            )
            new_count += 1
        if new_count:
            await session.commit()
            created += new_count
    return created
