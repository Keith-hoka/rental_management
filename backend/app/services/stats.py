from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Lease,
    MaintenanceRequest,
    MaintenanceStatus,
    Membership,
    Payment,
    Property,
    Role,
)
from app.schemas.stats import (
    DashboardStats,
    MaintenanceStatusCount,
    MonthlyIncome,
    OccupancyPoint,
)
from app.services.payments import org_charge_statuses, summarize


async def _count(session: AsyncSession, stmt) -> int:
    return (await session.execute(stmt)).scalar_one()


async def _collected_since(session: AsyncSession, organization_id, since: date) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.organization_id == organization_id, Payment.paid_on >= since
        )
    )
    return Decimal(result.scalar_one())


def _window_months(today: date) -> list[date]:
    """The first of each of the last six months, oldest first."""
    return [today.replace(day=1) - relativedelta(months=i) for i in range(5, -1, -1)]


async def _maintenance_by_status(
    session: AsyncSession, organization_id, since: date
) -> list[MaintenanceStatusCount]:
    """Requests raised since the given date, counted per status.

    Statuses with no requests are reported as zero so the chart legend does not
    appear and disappear between loads.
    """
    result = await session.execute(
        select(MaintenanceRequest.status, func.count())
        .where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.created_at >= since,
        )
        .group_by(MaintenanceRequest.status)
    )
    counts = dict(result.all())
    return [
        MaintenanceStatusCount(status=status.value, count=counts.get(status, 0))
        for status in MaintenanceStatus
    ]


async def _monthly_income(
    session: AsyncSession, organization_id, today: date
) -> list[MonthlyIncome]:
    months = _window_months(today)
    result = await session.execute(
        select(Payment.paid_on, Payment.amount).where(
            Payment.organization_id == organization_id, Payment.paid_on >= months[0]
        )
    )
    buckets: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for paid_on, amount in result.all():
        buckets[(paid_on.year, paid_on.month)] += amount
    return [
        MonthlyIncome(month=f"{d.year:04d}-{d.month:02d}", amount=buckets[(d.year, d.month)])
        for d in months
    ]


def _month_end(month_start: date) -> date:
    return month_start + relativedelta(months=1) - timedelta(days=1)


def occupancy_series(
    leases, property_dates: list[date], months: list[date]
) -> list[OccupancyPoint]:
    """Occupied share of the portfolio for each month.

    Numerator: distinct properties whose lease covers any part of the month, so a
    tenancy ending on the 3rd still counts for that month. Denominator: properties
    created on or before the month's end, not today's count -- buying property
    later would otherwise turn earlier months into a decline that never happened.
    """
    points = []
    for start in months:
        end = _month_end(start)
        total = sum(1 for created in property_dates if created <= end)
        occupied = len(
            {
                lease.property_id
                for lease in leases
                if lease.start_date <= end and start <= lease.end_date
            }
        )
        rate = round(occupied * 100 / total, 1) if total else 0.0
        points.append(
            OccupancyPoint(
                month=f"{start.year:04d}-{start.month:02d}",
                occupied=occupied,
                total=total,
                rate=rate,
            )
        )
    return points


async def dashboard_stats(session: AsyncSession, organization_id, today: date) -> DashboardStats:
    """Aggregate the organization's money and portfolio figures for the dashboard."""
    leases = (
        (await session.execute(select(Lease).where(Lease.organization_id == organization_id)))
        .scalars()
        .all()
    )
    # One pass for the organization: lease_balance issues two queries each, so
    # the old loop cost 2N.
    by_lease = await org_charge_statuses(session, organization_id, today)
    outstanding = Decimal("0")
    overdue = Decimal("0")
    for statuses in by_lease.values():
        # summarize needs total_paid only for credit, which the dashboard does
        # not read; the allocated total keeps it at zero without a third query.
        paid = sum((s.amount_paid for s in statuses), Decimal("0"))
        balance = summarize(statuses, paid, today)
        outstanding += balance.outstanding
        overdue += balance.overdue_amount

    active = [lease for lease in leases if lease.start_date <= today <= lease.end_date]
    # created_at rather than a count(): the same rows give both the total and
    # each month's denominator, so the occupancy series costs no extra query.
    property_dates = [
        created.date()
        for (created,) in (
            await session.execute(
                select(Property.created_at).where(Property.organization_id == organization_id)
            )
        ).all()
    ]
    properties_total = len(property_dates)
    months = _window_months(today)
    tenants = await _count(
        session,
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == organization_id, Membership.role == Role.tenant),
    )
    maintenance_open = await _count(
        session,
        select(func.count())
        .select_from(MaintenanceRequest)
        .where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.status.in_([MaintenanceStatus.open, MaintenanceStatus.in_progress]),
        ),
    )
    return DashboardStats(
        outstanding=outstanding,
        overdue=overdue,
        collected_this_month=await _collected_since(session, organization_id, today.replace(day=1)),
        properties_total=properties_total,
        properties_occupied=len({lease.property_id for lease in active}),
        active_leases=len(active),
        tenants=tenants,
        maintenance_open=maintenance_open,
        monthly_income=await _monthly_income(session, organization_id, today),
        occupancy=occupancy_series(leases, property_dates, months),
        maintenance_by_status=await _maintenance_by_status(session, organization_id, months[0]),
    )
